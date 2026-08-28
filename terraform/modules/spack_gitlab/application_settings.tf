# Instance-wide GitLab application settings.
#
# Values were captured from the production GitLab instance on 2026-08-12.
resource "gitlab_application_settings" "this" {
  # Require administrators to enable Admin Mode by re-authenticating for administrative tasks.
  admin_mode = false

  # Where to redirect users after logout.
  after_sign_out_path = ""

  # Text shown to the user after signing up.
  after_sign_up_text = ""

  # Enable or disable Akismet spam protection.
  akismet_enabled = false

  # Set to true to allow users to delete their accounts.
  allow_account_deletion = true

  # Set to true to allow group owners to manage LDAP.
  allow_group_owners_to_manage_ldap = true

  # Allow requests to the local network from system hooks.
  allow_local_requests_from_system_hooks = true

  # Allow requests to the local network from web hooks and services.
  allow_local_requests_from_web_hooks_and_services = false

  # Indicates whether users assigned up to the Guest role can create groups and personal projects.
  allow_project_creation_for_guest_and_below = true

  # Allow using a registration token to create a runner.
  allow_runner_registration_token = true

  # Maximum limit of AsciiDoc include directives being processed in any one document.
  asciidoc_max_includes = 32

  # Enable proxying of assets.
  asset_proxy_enabled = false

  # By default, we write to the authorized_keys file to support Git over SSH without additional configuration.
  authorized_keys_enabled = false

  # Automatically ban users who download more than max_number_of_repository_downloads unique projects in the configured time period.
  auto_ban_user_on_excessive_projects_download = false

  # Specify a domain to use by default for every project’s Auto Review Apps and Auto Deploy stages.
  auto_devops_domain = ""

  # Enable Auto DevOps for projects by default.
  auto_devops_enabled = false

  # Enabling this permits automatic allocation of purchased storage in a namespace.
  automatic_purchased_storage_allocation = false

  # Maximum simultaneous Direct Transfer batches to process.
  bulk_import_concurrent_pipeline_batch_limit = 25

  # Enable migrating GitLab groups by direct transfer.
  bulk_import_enabled = true

  # Maximum download file size when importing from source GitLab instances by direct transfer.
  bulk_import_max_download_file_size = 5120

  # Indicates whether users can create top-level groups.
  can_create_group = true

  # Enabling this makes only licensed EE features available to projects if the project namespace’s plan includes the feature or if the project is public.
  check_namespace_plan = false

  # The maximum number of includes per pipeline.
  ci_max_includes = 150

  # The maximum amount of memory, in bytes, that can be allocated for the pipeline configuration, with all included YAML configuration files.
  ci_max_total_yaml_size_bytes = 2147483647

  # Custom hostname (for private commit emails).
  commit_email_hostname = "users.noreply.gitlab.next.spack.io"

  # Maximum number of simultaneous import jobs for the Bitbucket Cloud importer.
  concurrent_bitbucket_import_jobs_limit = 100

  # Maximum number of simultaneous import jobs for the Bitbucket Server importer.
  concurrent_bitbucket_server_import_jobs_limit = 100

  # Maximum number of simultaneous import jobs for the GitHub importer.
  concurrent_github_import_jobs_limit = 1000

  # Enable cleanup policies for all projects.
  container_expiration_policies_enable_historic_entries = false

  # The maximum number of tags that can be deleted in a single execution of cleanup policies.
  container_registry_cleanup_tags_service_max_list_size = 200

  # The maximum time, in seconds, that the cleanup process can take to delete a batch of tags for cleanup policies.
  container_registry_delete_tags_service_timeout = 250

  # Caching during the execution of cleanup policies.
  container_registry_expiration_policies_caching = true

  # Number of workers for cleanup policies.
  container_registry_expiration_policies_worker_capacity = 4

  # Container Registry token duration in minutes.
  container_registry_token_expire_delay = 5

  # Enable automatic deactivation of dormant users.
  deactivate_dormant_users = false

  # Length of time (in days) after which a user is considered dormant.
  deactivate_dormant_users_period = 90

  # Default timeout for decompressing archived files, in seconds.
  decompress_archive_file_timeout = 210

  # Set the default expiration time for each job’s artifacts.
  default_artifacts_expire_in = "90 days"

  # Default CI/CD configuration file and path for new projects (.gitlab-ci.yml if not set).
  default_ci_config_path = ""

  # What visibility level new groups receive.
  default_group_visibility = "private"

  # Default preferred language for users who are not logged in.
  default_preferred_language = "en"

  # Default project creation protection.
  default_project_creation = 2

  # What visibility level new projects receive.
  default_project_visibility = "private"

  # Project limit per user.
  default_projects_limit = 100000

  # What visibility level new snippets receive.
  default_snippet_visibility = "private"

  # Default syntax highlighting theme for users who are new or not signed in.
  default_syntax_highlighting_theme = 1

  # Enable inactive project deletion feature.
  delete_inactive_projects = false

  # Specifies whether users who have not confirmed their email should be deleted.
  delete_unconfirmed_users = false

  # The number of days to wait before deleting a project or group that is marked for deletion.
  deletion_adjourned_period = 7

  # Enable Diagrams.net integration.
  diagramsnet_enabled = true

  # The Diagrams.net instance URL for integration.
  diagramsnet_url = "https://embed.diagrams.net"

  # Maximum files in a diff.
  diff_max_files = 1000

  # Maximum lines in a diff.
  diff_max_lines = 50000

  # Maximum diff patch size, in bytes.
  diff_max_patch_bytes = 204800

  # Stops administrators from connecting their GitLab accounts to non-trusted OAuth 2.0 applications that have the api, read_api, read_repository, write_repository, read_registry, write_registry, or sudo scopes.
  disable_admin_oauth_scopes = false

  # Disable display of RSS/Atom and calendar feed tokens (introduced in GitLab 13.7).
  disable_feed_token = false

  # Disable personal access tokens.
  disable_personal_access_tokens = false

  # Enforce DNS rebinding attack protection.
  dns_rebinding_protection_enabled = true

  # Allows blocking sign-ups from emails from specific domains.
  domain_denylist_enabled = false

  # Maximum downstream pipeline trigger rate.
  downstream_pipeline_trigger_limit_per_project_user_sha = 0

  # The minimum allowed bit length of an uploaded DSA key.
  dsa_key_restriction = 0

  # Indicates whether GitLab Duo features are enabled for this instance.
  duo_features_enabled = true

  # The minimum allowed curve size (in bits) of an uploaded ECDSA key.
  ecdsa_key_restriction = 0

  # The minimum allowed curve size (in bits) of an uploaded ECDSA_SK key.
  ecdsa_sk_key_restriction = 0

  # The minimum allowed curve size (in bits) of an uploaded ED25519 key.
  ed25519_key_restriction = 0

  # The minimum allowed curve size (in bits) of an uploaded ED25519_SK key.
  ed25519_sk_key_restriction = 0

  # Enable integration with Amazon EKS.
  eks_integration_enabled = false

  # Enable the use of AWS hosted Elasticsearch.
  elasticsearch_aws = false

  # The AWS region the Elasticsearch domain is configured.
  elasticsearch_aws_region = "us-east-1"

  # Maximum size of text fields to index by Elasticsearch.
  elasticsearch_indexed_field_length_limit = 0

  # Maximum size of repository and wiki files that are indexed by Elasticsearch.
  elasticsearch_indexed_file_size_limit_kb = 1024

  # Enable Elasticsearch indexing.
  elasticsearch_indexing = false

  # Limit Elasticsearch to index certain namespaces and projects.
  elasticsearch_limit_indexing = false

  # Maximum concurrency of Elasticsearch bulk requests per indexing operation.
  elasticsearch_max_bulk_concurrency = 10

  # Maximum size of Elasticsearch bulk indexing requests in MB.
  elasticsearch_max_bulk_size_mb = 10

  # Maximum concurrency of Elasticsearch code indexing background jobs.
  elasticsearch_max_code_indexing_concurrency = 30

  # Enable automatic requeuing of indexing workers.
  elasticsearch_requeue_workers = false

  # Enable Elasticsearch search.
  elasticsearch_search = false

  # The URL to use for connecting to Elasticsearch.
  elasticsearch_url = ["http://localhost:9200"]

  # Number of indexing worker shards.
  elasticsearch_worker_number_of_shards = 2

  # Some email servers do not support overriding the email sender name.
  email_author_in_body = false

  # Specifies whether users must confirm their email before sign in.
  email_confirmation_setting = "hard"

  # Show the external redirect page that warns you about user-generated content in GitLab Pages.
  enable_artifact_external_redirect_warning_page = true

  # Enabled protocols for Git access.
  enabled_git_access_protocol = "nil"

  # Enabling this permits enforcement of namespace storage limits.
  enforce_namespace_storage_limit = false

  # Enforce application ToS to all users.
  enforce_terms = false

  # Enable using an external authorization service for accessing projects.
  external_authorization_service_enabled = false

  # The timeout after which an authorization request is aborted, in seconds.
  external_authorization_service_timeout = 0.5

  # Start day of the week for calendar views and date pickers.
  first_day_of_week = 0

  # Comma-separated list of IPs and CIDRs of allowed secondary nodes.
  geo_node_allowed_ips = "0.0.0.0/0, ::/0"

  # The amount of seconds after which a request to get a secondary node status times out.
  geo_status_timeout = 10

  # List of user IDs that are emailed when the Git abuse rate limit is exceeded.
  git_rate_limit_users_alertlist = []

  # List of usernames excluded from Git anti-abuse rate limits.
  git_rate_limit_users_allowlist = []

  # Maximum duration (in minutes) of a session for Git operations when 2FA is enabled.
  git_two_factor_session_expiry = 15

  # Default Gitaly timeout, in seconds.
  gitaly_timeout_default = 55

  # Gitaly fast operation timeout, in seconds.
  gitaly_timeout_fast = 10

  # Medium Gitaly timeout, in seconds.
  gitaly_timeout_medium = 30

  # Maximum number of Git operations per minute a user can perform.
  gitlab_shell_operation_limit = 600

  # Enable Gitpod integration.
  gitpod_enabled = false

  # The Gitpod instance URL for integration.
  gitpod_url = "https://gitpod.io/"

  # Comma-separated list of IP addresses and CIDRs always allowed for inbound traffic.
  globally_allowed_ips = ""

  # Enable Grafana.
  grafana_enabled = false

  # Grafana URL.
  grafana_url = "/-/grafana"

  # Enable Gravatar.
  gravatar_enabled = true

  # Prevent overrides of default branch protection.
  group_owners_can_manage_default_branch_protection = true

  # Hide marketing-related entries from help.
  help_page_hide_commercial_content = false

  # Do not display offers from third parties in GitLab.
  hide_third_party_offers = false

  # Redirect to this URL when not logged in.
  home_page_url = ""

  # Enable or disable Git housekeeping.
  housekeeping_enabled = true

  # Number of Git pushes after which an incremental git repack is run.
  housekeeping_optimize_repository_period = 10

  # Enable HTML emails.
  html_emails_enabled = true

  # Sources to allow project import from.
  import_sources = ["github", "bitbucket", "bitbucket_server", "fogbugz", "git", "gitlab_project", "gitea", "manifest"]

  # If delete_inactive_projects is true, the time (in months) to wait before deleting inactive projects.
  inactive_projects_delete_after_months = 2

  # If delete_inactive_projects is true, the minimum repository size for projects to be checked for inactivity.
  inactive_projects_min_size_mb = 0

  # If delete_inactive_projects is true, sets the time (in months) to wait before emailing maintainers that the project is scheduled be deleted because it is inactive.
  inactive_projects_send_warning_email_after_months = 1

  # Whether or not optional metrics are enabled in Service Ping.
  include_optional_metrics_in_service_ping = true

  # Enable Invisible CAPTCHA spam detection during sign-up.
  invisible_captcha_enabled = false

  # Max number of issue creation requests per minute per user.
  issues_create_limit = 300

  # Enable public key storage for the GitLab for Jira Cloud app.
  jira_connect_public_key_storage_enabled = false

  # Prevent the deletion of the artifacts from the most recent successful jobs, regardless of the expiry time.
  keep_latest_artifact = false

  # Increase this value when any cached Markdown should be invalidated.
  local_markdown_version = 0

  # Indicates whether the GitLab Duo features enabled setting is enforced for all subgroups.
  lock_duo_features_enabled = false

  # Enable Mailgun event receiver.
  mailgun_events_enabled = false

  # When instance is in maintenance mode, non-administrative users can sign in with read-only access and make read-only API requests.
  maintenance_mode = false

  # Set the maintenance mode message explicity.
  maintenance_mode_message = "Gitlab is undergoing scheduled maintenance. If you are experiencing issues, please try again later."

  # Use repo.maven.apache.org as a default remote repository when the package is not found in the GitLab Package Registry for Maven.
  maven_package_requests_forwarding = true

  # Maximum artifacts size in MB.
  max_artifacts_size = 10000

  # Limit attachment size in MB.
  max_attachment_size = 10

  # Maximum decompressed archive size in bytes.
  max_decompressed_archive_size = 25600

  # Maximum export size in MB.
  max_export_size = 0

  # Maximum remote file size for imports from external object storages.
  max_import_remote_file_size = 10240

  # Maximum import size in MB.
  max_import_size = 0

  # Maximum number of unique repositories a user can download in the specified time period before they are banned.
  max_number_of_repository_downloads = 0

  # Reporting time period (in seconds).
  max_number_of_repository_downloads_within_time_period = 0

  # Maximum size of pages repositories in MB.
  max_pages_size = 100

  # Maximum size in bytes of the Terraform state files.
  max_terraform_state_size_bytes = 0

  # Maximum size in bytes of a CI/CD configuration YAML file.
  max_yaml_size_bytes = 52428800

  # Maximum depth of nested CI/CD configuration added with the 'include' keyword.
  max_yaml_depth = 100

  # A method call is only tracked when it takes longer than the given amount of milliseconds.
  metrics_method_call_threshold = 10

  # Indicates whether passwords require a minimum length.
  minimum_password_length = 8

  # Allow repository mirroring to configured by project Maintainers.
  mirror_available = true

  # Minimum capacity to be available before scheduling more mirrors preemptively.
  mirror_capacity_threshold = 15

  # Maximum number of mirrors that can be synchronizing at the same time.
  mirror_max_capacity = 30

  # Maximum time (in minutes) between updates that a mirror can have when scheduled to synchronize.
  mirror_max_delay = 300

  # Use npmjs.org as a default remote repository when the package is not found in the GitLab Package Registry for npm.
  npm_package_requests_forwarding = true

  # Define a list of trusted domains or IP addresses to which local requests are allowed when local requests for hooks and services are disabled.
  outbound_local_requests_whitelist = ["webhook-handler.custom.svc.cluster.local", "spack-gantry.spack.svc.cluster.local"]

  # List of package registry metadata to sync.
  package_metadata_purl_types = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 17]

  # Enable to allow anyone to pull from Package Registry visible and changeable.
  package_registry_allow_anyone_to_pull_option = true

  # Number of workers assigned to the packages cleanup policies.
  package_registry_cleanup_policies_worker_capacity = 2

  # Require users to prove ownership of custom domains.
  pages_domain_verification_enabled = true

  # Enable authentication for Git over HTTP(S) via a GitLab account password.
  password_authentication_enabled_for_git = true

  # Enable authentication for the web interface via a GitLab account password.
  password_authentication_enabled_for_web = true

  # Indicates whether passwords require at least one lowercase letter.
  password_lowercase_required = false

  # Indicates whether passwords require at least one number.
  password_number_required = false

  # Indicates whether passwords require at least one symbol character.
  password_symbol_required = false

  # Indicates whether passwords require at least one uppercase letter.
  password_uppercase_required = false

  # Prefix for all generated personal access tokens.
  personal_access_token_prefix = "glpat-"

  # Maximum number of pipeline creation requests per minute per user and commit.
  pipeline_limit_per_project_user_sha = 0

  # Enable PlantUML integration.
  plantuml_enabled = false

  # Interval multiplier used by endpoints that perform polling.
  polling_interval_multiplier = 1

  # Enable project export.
  project_export_enabled = true

  # Maximum authenticated requests to /project/:id/jobs per minute.
  project_jobs_api_rate_limit = 600

  # Introduced in GitLab 15.10.
  projects_api_rate_limit_unauthenticated = 400

  # Enable Prometheus metrics.
  prometheus_metrics_enabled = true

  # CI/CD variables are protected by default.
  protected_ci_variables = true

  # Number of changes (branches or tags) in a single push to determine whether individual push events or bulk push events are created.
  push_event_activities_limit = 3

  # Number of changes (branches or tags) in a single push to determine whether webhooks and services fire or not.
  push_event_hooks_limit = 3

  # Use pypi.org as a default remote repository when the package is not found in the GitLab Package Registry for PyPI.
  pypi_package_requests_forwarding = true

  # Max number of requests per minute for each raw path.
  raw_blob_request_limit = 300

  # Enable reCAPTCHA.
  recaptcha_enabled = false

  # Enable Remember me setting.
  remember_me_enabled = true

  # GitLab periodically runs git fsck in all project and wiki repositories to look for silent disk corruption issues.
  repository_checks_enabled = true

  # Size limit per repository (MB).
  repository_size_limit = 0

  # Hash of names of taken from gitlab.yml to weights.
  repository_storages_weighted = { default = 100 }

  # When enabled, any user that signs up for an account using the registration form is placed under a Pending approval state and has to be explicitly approved by an administrator.
  require_admin_approval_after_user_signup = true

  # Allow administrators to require 2FA for all administrators on the instance.
  require_admin_two_factor_authentication = true

  # When enabled, users must set an expiration date when creating a group or project access token, or a personal access token owned by a non-service account.
  require_personal_access_token_expiry = true

  # Require all users to set up Two-factor authentication.
  require_two_factor_authentication = true

  # Selected levels cannot be used by non-Administrator users for groups, projects or snippets.
  restricted_visibility_levels = []

  # The minimum allowed bit length of an uploaded RSA key.
  rsa_key_restriction = 0

  # Max number of requests per minute for performing a search while authenticated.
  search_rate_limit = 300

  # Max number of requests per minute for performing a search while unauthenticated.
  search_rate_limit_unauthenticated = 100

  # Maximum number of active merge request approval policies per security policy project.
  security_approval_policies_limit = 5

  # Whether to look up merge request approval policy approval groups globally or within project hierarchies.
  security_policy_global_group_approvers_enabled = true

  # Flag to indicate if token expiry date can be optional for service account users.
  service_access_tokens_expiration_enforced = true

  # Session duration in minutes.
  session_expire_delay = 10080

  # Enable shared runners for new projects.
  shared_runners_enabled = true

  # Set the maximum number of CI/CD minutes that a group can use on shared runners per month.
  shared_runners_minutes = 0

  # Shared runners text.
  shared_runners_text = ""

  # The threshold in bytes at which Sidekiq jobs are compressed before being stored in Redis.
  sidekiq_job_limiter_compression_threshold_bytes = 100000

  # The threshold in bytes at which Sidekiq jobs are rejected.
  sidekiq_job_limiter_limit_bytes = 0

  # Behavior for Sidekiq job size limits: track or compress.
  sidekiq_job_limiter_mode = "compress"

  # Enable registration.
  signup_enabled = false

  # Enable Silent admin exports.
  silent_admin_exports_enabled = false

  # Enable Silent mode.
  silent_mode_enabled = false

  # Enable Slack app.
  slack_app_enabled = false

  # Max snippet content size in bytes.
  snippet_size_limit = 52428800

  # Enable snowplow tracking.
  snowplow_enabled = false

  # Enables Sourcegraph integration.
  sourcegraph_enabled = false

  # Blocks Sourcegraph from being loaded on private and internal projects.
  sourcegraph_public_only = true

  # Enables spam checking using external Spam Check API endpoint.
  spam_check_endpoint_enabled = false

  # Enable pipeline suggestion banner.
  suggest_pipeline_enabled = true

  # Maximum time for web terminal websocket connection (in seconds).
  terminal_max_session_time = 0

  # Enable authenticated API request rate limit.
  throttle_authenticated_api_enabled = false

  # Rate limit period (in seconds).
  throttle_authenticated_api_period_in_seconds = 3600

  # Maximum requests per period per user.
  throttle_authenticated_api_requests_per_period = 7200

  # Enable authenticated API request rate limit.
  throttle_authenticated_packages_api_enabled = false

  # Rate limit period (in seconds).
  throttle_authenticated_packages_api_period_in_seconds = 15

  # Maximum requests per period per user.
  throttle_authenticated_packages_api_requests_per_period = 1000

  # Enable authenticated web request rate limit.
  throttle_authenticated_web_enabled = false

  # Rate limit period (in seconds).
  throttle_authenticated_web_period_in_seconds = 3600

  # Maximum requests per period per user.
  throttle_authenticated_web_requests_per_period = 7200

  # Enable unauthenticated API request rate limit.
  throttle_unauthenticated_api_enabled = false

  # Rate limit period in seconds.
  throttle_unauthenticated_api_period_in_seconds = 3600

  # Max requests per period per IP.
  throttle_unauthenticated_api_requests_per_period = 3600

  # Enable authenticated API request rate limit.
  throttle_unauthenticated_packages_api_enabled = false

  # Rate limit period (in seconds).
  throttle_unauthenticated_packages_api_period_in_seconds = 15

  # Maximum requests per period per user.
  throttle_unauthenticated_packages_api_requests_per_period = 800

  # Enable unauthenticated web request rate limit.
  throttle_unauthenticated_web_enabled = false

  # Rate limit period in seconds.
  throttle_unauthenticated_web_period_in_seconds = 3600

  # Max requests per period per IP.
  throttle_unauthenticated_web_requests_per_period = 3600

  # Limit display of time tracking units to hours.
  time_tracking_limit_to_hours = false

  # Amount of time (in hours) that users are allowed to skip forced configuration of two-factor authentication.
  two_factor_grace_period = 0

  # Specifies how many days after sign-up to delete users who have not confirmed their email.
  unconfirmed_users_delete_after_days = 7

  # Limit sign in from multiple IPs.
  unique_ips_limit_enabled = false

  # Maximum number of IPs per user.
  unique_ips_limit_per_user = 10

  # How many seconds an IP is counted towards the limit.
  unique_ips_limit_time_window = 3600

  # Fetch GitLab Runner release version data from GitLab.com.
  update_runner_versions_enabled = true

  # Every week GitLab reports license usage back to GitLab, Inc.
  usage_ping_enabled = true

  # Send an email to users upon account deactivation.
  user_deactivation_emails_enabled = true

  # Newly registered users are external by default.
  user_default_external = false

  # Newly created users have private profile by default.
  user_defaults_to_private_profile = false

  # Allow users to register any application to use GitLab as an OAuth provider.
  user_oauth_applications = true

  # When set to false disable the You won't be able to pull or push project code via SSH warning shown to users with no uploaded SSH key.
  user_show_add_ssh_key_message = true

  # List of types which are allowed to register a GitLab Runner.
  valid_runner_registrars = ["project", "group"]

  # Let GitLab inform you when an update is available.
  version_check_enabled = true

  # What's new variant, possible values: all_tiers, current_tier, and disabled.
  whats_new_variant = "all_tiers"

  # Maximum wiki page content size in bytes.
  wiki_page_max_content_bytes = 5242880

  # The default_branch_protection_defaults attribute describes the default branch protection defaults.
  default_branch_protection_defaults {
    # Allow force push for all users with push access.
    allow_force_push = false

    # An array of access levels allowed to merge.
    allowed_to_merge = [40]

    # An array of access levels allowed to push.
    allowed_to_push = [40]
  }
}
