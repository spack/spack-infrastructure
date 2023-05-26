# Retrieve the master password for the gitlab clone production database
data "aws_secretsmanager_secret" "gitlab_db_clone_credentials" {
  count = var.gitlab_db_clone_master_credentials_secret == "" ? 0 : 1
  arn   = var.gitlab_db_clone_master_credentials_secret
}
data "aws_secretsmanager_secret_version" "gitlab_db_clone_credentials" {
  count     = var.gitlab_db_clone_master_credentials_secret == "" ? 0 : 1
  secret_id = data.aws_secretsmanager_secret.gitlab_db_clone_credentials[0].id
}

# Compute local values required in the gitlab_db module
locals {
  gitlab_db_clone_master_password = var.gitlab_db_clone_master_credentials_secret == "" ? "" : jsondecode(data.aws_secretsmanager_secret_version.gitlab_db_clone_credentials[0].secret_string)["password"]
}


# The definition for the RDS instance that clones from the main gitlab RDS instance
module "gitlab_db_clone" {
  count = var.provision_monitoring_db ? 1 : 0

  source  = "terraform-aws-modules/rds/aws"
  version = "5.2.3"

  identifier = "gitlab-${var.deployment_name}-clone"

  engine               = "postgres"
  engine_version       = "14.6"
  family               = "postgres14"
  major_engine_version = "14"
  instance_class       = var.gitlab_db_instance_class

  db_name                = "gitlabhq_production"
  username               = "postgres"
  port                   = "5432"
  create_random_password = false
  password               = local.gitlab_db_clone_master_password

  publicly_accessible  = false
  db_subnet_group_name = aws_db_subnet_group.spack.name


  maintenance_window              = "Sun:00:00-Sun:03:00"
  backup_window                   = "03:00-06:00"
  enabled_cloudwatch_logs_exports = ["postgresql", "upgrade"]
  create_cloudwatch_log_group     = true

  backup_retention_period = 7
  skip_final_snapshot     = false
  deletion_protection     = true

  allocated_storage     = 500
  max_allocated_storage = 1000

  vpc_security_group_ids = [module.postgres_security_group.security_group_id]
}


# Defines the Change Data Capture migration between the source and clone RDS instances
module "database_migration_service" {
  count = var.provision_monitoring_db ? 1 : 0

  source  = "terraform-aws-modules/dms/aws"
  version = "~> 1.6"

  # Subnet group
  repl_subnet_group_name        = "dms-subnet-group"
  repl_subnet_group_description = "DMS Subnet group"
  repl_subnet_group_subnet_ids  = module.vpc.private_subnets

  # Instance
  repl_instance_id                           = "gitlab-db-sync-replication-instance"
  repl_instance_allocated_storage            = 64
  repl_instance_auto_minor_version_upgrade   = true
  repl_instance_allow_major_version_upgrade  = true
  repl_instance_apply_immediately            = true
  repl_instance_engine_version               = "3.4.7" # Must use 3.4.7 to support Postgres 14.x
  repl_instance_multi_az                     = true
  repl_instance_preferred_maintenance_window = "sun:10:30-sun:14:30"
  repl_instance_publicly_accessible          = false
  repl_instance_class                        = "dms.t3.large"

  # Endpoints
  endpoints = {
    source = {
      # Required
      endpoint_id   = "gitlab-db-source-endpoint"
      endpoint_type = "source"
      engine_name   = "postgres"
      # Optional
      database_name = module.gitlab_db.db_instance_name
      username      = module.gitlab_db.db_instance_username
      password      = local.gitlab_db_master_password
      port          = module.gitlab_db.db_instance_port
      server_name   = module.gitlab_db.db_instance_address
      tags          = { EndpointType = "source" }
    }

    destination = {
      # Required
      endpoint_id   = "gitlab-db-target-endpoint"
      endpoint_type = "target"
      engine_name   = "postgres"
      # Optional
      database_name = module.gitlab_db_clone[0].db_instance_name
      username      = module.gitlab_db_clone[0].db_instance_username
      password      = local.gitlab_db_clone_master_password
      port          = module.gitlab_db_clone[0].db_instance_port
      server_name   = module.gitlab_db_clone[0].db_instance_address
      tags          = { EndpointType = "destination" }
    }
  }

  replication_tasks = {
    cdc_ex = {
      replication_task_id = "gitlab-db-clone-cdc"
      migration_type      = "full-load-and-cdc"
      source_endpoint_key = "source"
      target_endpoint_key = "destination"
      table_mappings = jsonencode({
        "rules" : [
          {
            "rule-type" : "selection",
            "rule-id" : "1",
            "rule-name" : "select-all-tables",
            "object-locator" : {
              "schema-name" : "public",
              "table-name" : "%"
            },
            "rule-action" : "include",
            "filters" : []
          },
          # ########################################
          # Drop sensitive columns from users tables
          # ########################################
          {
            "rule-type" : "transformation",
            "rule-id" : "2",
            "rule-name" : "remove-users-sensitive-columns-1",
            "rule-action" : "remove-column",
            "rule-target" : "column",
            "object-locator" : {
              "schema-name" : "public",
              "table-name" : "users",
              "column-name" : "%encrypted%"
            },
            "filters" : []
          },
          {
            "rule-type" : "transformation",
            "rule-id" : "3",
            "rule-name" : "remove-users-sensitive-columns-2",
            "rule-action" : "remove-column",
            "rule-target" : "column",
            "object-locator" : {
              "schema-name" : "public",
              "table-name" : "users",
              "column-name" : "%token%"
            },
            "filters" : []
          },
          {
            "rule-type" : "transformation",
            "rule-id" : "4",
            "rule-name" : "remove-users-sensitive-columns-3",
            "rule-action" : "remove-column",
            "rule-target" : "column",
            "object-locator" : {
              "schema-name" : "public",
              "table-name" : "users",
              "column-name" : "%ip%"
            },
            "filters" : []
          },
          # ##########################
          # Exclude unnecessary tables
          # ##########################
          {
            "rule-type" : "selection",
            "rule-id" : "5",
            "rule-name" : "exclude-ci-build-needs",
            "object-locator" : {
              "schema-name" : "public",
              "table-name" : "ci_build_needs"
            },
            "rule-action" : "exclude",
            "filters" : []
          },
          {
            "rule-type" : "selection",
            "rule-id" : "6",
            "rule-name" : "exclude-ci-builds-metadata",
            "object-locator" : {
              "schema-name" : "public",
              "table-name" : "ci_builds_metadata"
            },
            "rule-action" : "exclude",
            "filters" : []
          },
          {
            "rule-type" : "selection",
            "rule-id" : "7",
            "rule-name" : "exclude-ci-build-trace-metadata",
            "object-locator" : {
              "schema-name" : "public",
              "table-name" : "ci_build_trace_metadata"
            },
            "rule-action" : "exclude",
            "filters" : []
          },
          {
            "rule-type" : "selection",
            "rule-id" : "8",
            "rule-name" : "exclude-ci-job-artifacts",
            "object-locator" : {
              "schema-name" : "public",
              "table-name" : "ci_job_artifacts"
            },
            "rule-action" : "exclude",
            "filters" : []
          },
          {
            "rule-type" : "selection",
            "rule-id" : "9",
            "rule-name" : "exclude-ci-pipeline-variables",
            "object-locator" : {
              "schema-name" : "public",
              "table-name" : "ci_pipeline_variables"
            },
            "rule-action" : "exclude",
            "filters" : []
          },
          {
            "rule-type" : "selection",
            "rule-id" : "10",
            "rule-name" : "exclude-loose-foreign-keys",
            "object-locator" : {
              "schema-name" : "public",
              "table-name" : "loose_foreign_keys_deleted_records"
            },
            "rule-action" : "exclude",
            "filters" : []
          },
          {
            "rule-type" : "selection",
            "rule-id" : "11",
            "rule-name" : "exclude-web-hook-logs",
            "object-locator" : {
              "schema-name" : "public",
              "table-name" : "web_hook_logs"
            },
            "rule-action" : "exclude",
            "filters" : []
          }
        ]
      })
      replication_task_settings = jsonencode({
        "BeforeImageSettings" : null,
        "ChangeProcessingDdlHandlingPolicy" : {
          "HandleSourceTableAltered" : true,
          "HandleSourceTableDropped" : true,
          "HandleSourceTableTruncated" : true
        },
        "ChangeProcessingTuning" : {
          "BatchApplyMemoryLimit" : 500,
          "BatchApplyPreserveTransaction" : true,
          "BatchApplyTimeoutMax" : 30,
          "BatchApplyTimeoutMin" : 1,
          "BatchSplitSize" : 0,
          "CommitTimeout" : 1,
          "MemoryKeepTime" : 60,
          "MemoryLimitTotal" : 1024,
          "MinTransactionSize" : 1000,
          "StatementCacheSize" : 50
        },
        "CharacterSetSettings" : null,
        "ControlTablesSettings" : {
          "ControlSchema" : "",
          "FullLoadExceptionTableEnabled" : false,
          "HistoryTableEnabled" : false,
          "HistoryTimeslotInMinutes" : 5,
          "StatusTableEnabled" : false,
          "SuspendedTablesTableEnabled" : false
        },
        "ErrorBehavior" : {
          "ApplyErrorDeletePolicy" : "IGNORE_RECORD",
          "ApplyErrorEscalationCount" : 0,
          "ApplyErrorEscalationPolicy" : "LOG_ERROR",
          "ApplyErrorFailOnTruncationDdl" : false,
          "ApplyErrorInsertPolicy" : "LOG_ERROR",
          "ApplyErrorUpdatePolicy" : "LOG_ERROR",
          "DataErrorEscalationCount" : 0,
          "DataErrorEscalationPolicy" : "SUSPEND_TABLE",
          "DataErrorPolicy" : "LOG_ERROR",
          "DataTruncationErrorPolicy" : "LOG_ERROR",
          "EventErrorPolicy" : "IGNORE",
          "FailOnNoTablesCaptured" : true,
          "FailOnTransactionConsistencyBreached" : false,
          "FullLoadIgnoreConflicts" : true,
          "RecoverableErrorCount" : -1,
          "RecoverableErrorInterval" : 5,
          "RecoverableErrorStopRetryAfterThrottlingMax" : true,
          "RecoverableErrorThrottling" : true,
          "RecoverableErrorThrottlingMax" : 1800,
          "TableErrorEscalationCount" : 0,
          "TableErrorEscalationPolicy" : "STOP_TASK",
          "TableErrorPolicy" : "SUSPEND_TABLE"
        },
        "FailTaskWhenCleanTaskResourceFailed" : false,
        "FullLoadSettings" : {
          "CommitRate" : 10000,
          "CreatePkAfterFullLoad" : false,
          "MaxFullLoadSubTasks" : 8,
          "StopTaskCachedChangesApplied" : false,
          "StopTaskCachedChangesNotApplied" : false,
          "TargetTablePrepMode" : "DO_NOTHING",
          "TransactionConsistencyTimeout" : 600
        },
        "Logging" : {
          "EnableLogContext" : false,
          "EnableLogging" : true,
          "LogComponents" : [
            {
              "Id" : "TRANSFORMATION",
              "Severity" : "LOGGER_SEVERITY_DEFAULT"
            },
            {
              "Id" : "SOURCE_UNLOAD",
              "Severity" : "LOGGER_SEVERITY_DEFAULT"
            },
            {
              "Id" : "IO",
              "Severity" : "LOGGER_SEVERITY_DEFAULT"
            },
            {
              "Id" : "TARGET_LOAD",
              "Severity" : "LOGGER_SEVERITY_DEFAULT"
            },
            {
              "Id" : "PERFORMANCE",
              "Severity" : "LOGGER_SEVERITY_DEFAULT"
            },
            {
              "Id" : "SOURCE_CAPTURE",
              "Severity" : "LOGGER_SEVERITY_DEFAULT"
            },
            {
              "Id" : "SORTER",
              "Severity" : "LOGGER_SEVERITY_DEFAULT"
            },
            {
              "Id" : "REST_SERVER",
              "Severity" : "LOGGER_SEVERITY_DEFAULT"
            },
            {
              "Id" : "VALIDATOR_EXT",
              "Severity" : "LOGGER_SEVERITY_DEFAULT"
            },
            {
              "Id" : "TARGET_APPLY",
              "Severity" : "LOGGER_SEVERITY_DEFAULT"
            },
            {
              "Id" : "TASK_MANAGER",
              "Severity" : "LOGGER_SEVERITY_DEFAULT"
            },
            {
              "Id" : "TABLES_MANAGER",
              "Severity" : "LOGGER_SEVERITY_DEFAULT"
            },
            {
              "Id" : "METADATA_MANAGER",
              "Severity" : "LOGGER_SEVERITY_DEFAULT"
            },
            {
              "Id" : "FILE_FACTORY",
              "Severity" : "LOGGER_SEVERITY_DEFAULT"
            },
            {
              "Id" : "COMMON",
              "Severity" : "LOGGER_SEVERITY_DEFAULT"
            },
            {
              "Id" : "ADDONS",
              "Severity" : "LOGGER_SEVERITY_DEFAULT"
            },
            {
              "Id" : "DATA_STRUCTURE",
              "Severity" : "LOGGER_SEVERITY_DEFAULT"
            },
            {
              "Id" : "COMMUNICATION",
              "Severity" : "LOGGER_SEVERITY_DEFAULT"
            },
            {
              "Id" : "FILE_TRANSFER",
              "Severity" : "LOGGER_SEVERITY_DEFAULT"
            }
          ]
        },
        "LoopbackPreventionSettings" : null,
        "PostProcessingRules" : null,
        "StreamBufferSettings" : {
          "CtrlStreamBufferSizeInMB" : 5,
          "StreamBufferCount" : 3,
          "StreamBufferSizeInMB" : 8
        },
        "TTSettings" : {
          "EnableTT" : false,
          "TTRecordSettings" : null,
          "TTS3Settings" : null
        },
        "TargetMetadata" : {
          "BatchApplyEnabled" : true,
          "FullLobMode" : true,
          "InlineLobMaxSize" : 0,
          "LimitedSizeLobMode" : false,
          "LoadMaxFileSize" : 0,
          "LobChunkSize" : 64,
          "LobMaxSize" : 0,
          "ParallelApplyBufferSize" : 0,
          "ParallelApplyQueuesPerThread" : 0,
          "ParallelApplyThreads" : 0,
          "ParallelLoadBufferSize" : 0,
          "ParallelLoadQueuesPerThread" : 0,
          "ParallelLoadThreads" : 0,
          "SupportLobs" : true,
          "TargetSchema" : "",
          "TaskRecoveryTableEnabled" : false
        }
      })
    }
  }
}
