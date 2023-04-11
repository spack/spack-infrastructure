module "postgres_security_group" {
  source  = "terraform-aws-modules/security-group/aws"
  version = "4.16.2"

  name        = "postgres_sg"
  description = "Security group for RDS PostgreSQL database"
  vpc_id      = module.vpc.vpc_id

  ingress_with_cidr_blocks = [
    {
      from_port   = 5432
      to_port     = 5432
      protocol    = "tcp"
      description = "PostgreSQL access from within VPC"
      cidr_blocks = module.vpc.vpc_cidr_block
    },
  ]
}

# Retrieve the master password for the gitlab production database,
# since it has been changed since terraform created the RDS instance
data "aws_secretsmanager_secret" "gitlab_db_credentials" {
  arn = var.gitlab_db_master_credentials_secret
}
data "aws_secretsmanager_secret_version" "gitlab_db_credentials" {
  secret_id = data.aws_secretsmanager_secret.gitlab_db_credentials.id
}

# Determine the corresponding EC2 instance size, in order to retrieve the memory and vcpu size
locals {
  gitlab_db_instance_ec2_class = replace(var.gitlab_db_instance_class, "db.", "")
}
data "aws_ec2_instance_type" "gitlab_db_instance_type" {
  instance_type = local.gitlab_db_instance_ec2_class
}

# Compute local values required in the gitlab_db module
locals {
  gitlab_db_master_password = jsondecode(data.aws_secretsmanager_secret_version.gitlab_db_credentials.secret_string)["password"]

  # Computed values for the parameters. The formulas for these values are taken from the
  # existing settings, encoding them here as the DSL for RDS parameters is insufficient
  max_logical_replication_workers = 4
  instance_type_memory_bytes      = data.aws_ec2_instance_type.gitlab_db_instance_type.memory_size * 1049000
  autovacuum_max_workers          = max(local.instance_type_memory_bytes / 64371566592, 3)
  max_parallel_workers            = max(data.aws_ec2_instance_type.gitlab_db_instance_type.default_vcpus / 2, 8)
  max_worker_processes            = sum([local.max_logical_replication_workers, local.autovacuum_max_workers, local.max_parallel_workers])
}

module "gitlab_db" {
  source  = "terraform-aws-modules/rds/aws"
  version = "5.2.3"

  identifier = "gitlab-${var.deployment_name}"

  engine               = "postgres"
  engine_version       = "14.3"
  family               = "postgres14"
  major_engine_version = "14"
  instance_class       = var.gitlab_db_instance_class

  db_name  = "gitlabhq_production"
  username = "postgres"
  port     = "5432"

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

  # Set parameters in the automatically created parameter group to allow DMS to work correctly
  create_db_parameter_group = true
  parameters = [
    # Enable logical replication so CDCs can be run correctly
    {
      name         = "rds.logical_replication"
      value        = "1"
      apply_method = "pending-reboot"
    },
    # Ensure a timeout of at least 10000 (10s)
    {
      name         = "wal_sender_timeout"
      value        = "30000"
      apply_method = "pending-reboot"
    },
    # Explicitly set the max number of logical replication, autovacuum, and parallel workers.
    # The value of these parameters are stated here in order to encode them explicitly,
    # and are the values from the existing parameter group.
    {
      name         = "max_logical_replication_workers",
      value        = local.max_logical_replication_workers
      apply_method = "pending-reboot"
    },
    {
      name         = "autovacuum_max_workers",
      value        = local.autovacuum_max_workers
      apply_method = "pending-reboot"
    },
    {
      name         = "max_parallel_workers",
      value        = local.max_parallel_workers
      apply_method = "pending-reboot"
    },

    # The AWS docs highlight that this value should be at least the sum of the
    # 3 preceeding parameters, which is why they're defined here.
    {
      name         = "max_worker_processes"
      value        = local.max_worker_processes
      apply_method = "pending-reboot"
    }
  ]
}

# The definition for the RDS instance that clones from the main gitlab RDS instance
module "gitlab_db_clone" {
  source  = "terraform-aws-modules/rds/aws"
  version = "5.2.3"

  identifier = "gitlab-${var.deployment_name}-clone"

  engine               = "postgres"
  engine_version       = "14"
  family               = "postgres14"
  major_engine_version = "14"
  instance_class       = var.gitlab_db_instance_class

  db_name  = "gitlabhq_production"
  username = "postgres"
  port     = "5432"

  publicly_accessible  = false
  db_subnet_group_name = module.vpc.database_subnet_group

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
  source  = "terraform-aws-modules/dms/aws"
  version = "~> 1.6"

  # Subnet group
  repl_subnet_group_name        = "dms-subnet-group"
  repl_subnet_group_description = "DMS Subnet group"
  repl_subnet_group_subnet_ids  = var.private_subnets

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
      database_name = module.gitlab_db_clone.db_instance_name
      username      = module.gitlab_db_clone.db_instance_username
      password      = module.gitlab_db_clone.db_instance_password
      port          = module.gitlab_db_clone.db_instance_port
      server_name   = module.gitlab_db_clone.db_instance_address
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
            "rule-id" : "149415118",
            "rule-name" : "select-all-tables",
            "object-locator" : {
              "schema-name" : "%",
              "table-name" : "%"
            },
            "rule-action" : "include",
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
