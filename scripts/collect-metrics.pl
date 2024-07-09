#!/usr/bin/perl -w

our $usage = <<USAGE;
USAGE

use strict;
use warnings;
use Getopt::Long;
use File::Basename;
use Sys::Hostname;
use Sys::Syslog qw(:DEFAULT setlogsock);
use Sys::Syslog qw(:standard :macros);

BEGIN
{
  my $script_dir = &File::Basename::dirname($0);
  push @INC, $script_dir;
}

use CloudWatchClient;

use constant
{
  KILO => 1024,
  MEGA => 1048576,
  GIGA => 1073741824,
};

use constant
{
  INCL_AGGREGATED => 1,
  AGGREGATED_ONLY => 2,
};

use constant
{
  NOW => 0,
};

my $version = '1.2.2';
my $client_name = 'CloudWatch-PutInstanceData';

my $mcount = 0;
my $report_mem_util;
my $report_mem_used;
my $report_mem_avail;
my $report_swap_util;
my $report_swap_used;
my $report_disk_util;
my $report_disk_used;
my $report_disk_avail;
my $mem_used_incl_cache_buff;
my @mount_path;
my $mem_units;
my $disk_units;
my $mem_unit_div = 1;
my $disk_unit_div = 1;
my $aggregated;
my $auto_scaling; 	 
my $from_cron;
my $verify;
my $verbose;
my $show_help;
my $show_version;
my $enable_compression;
my $aws_credential_file;
my $aws_access_key_id;
my $aws_secret_key;
my $aws_iam_role;
my $parse_result = 1;
my $parse_error = '';
my $argv_size = @ARGV;

{
  # Capture warnings from GetOptions
  local $SIG{__WARN__} = sub { $parse_error .= $_[0]; };

  $parse_result = GetOptions(
    'help|?' => \$show_help,
    'version' => \$show_version,
    'mem-util' => \$report_mem_util,
    'mem-used' => \$report_mem_used,
    'mem-avail' => \$report_mem_avail,
    'swap-util' => \$report_swap_util,
    'swap-used' => \$report_swap_used,
    'disk-path:s' => \@mount_path,
    'disk-space-util' => \$report_disk_util,
    'disk-space-used' => \$report_disk_used,
    'disk-space-avail' => \$report_disk_avail,
    'auto-scaling:s' => \$auto_scaling,
    'aggregated:s' => \$aggregated,
    'memory-units:s' => \$mem_units,
    'disk-space-units:s' => \$disk_units,
    'mem-used-incl-cache-buff' => \$mem_used_incl_cache_buff,
    'verify' => \$verify,
    'from-cron' => \$from_cron,
    'verbose' => \$verbose,
    'aws-credential-file:s' => \$aws_credential_file,
    'aws-access-key-id:s' => \$aws_access_key_id,
    'aws-secret-key:s' => \$aws_secret_key,
    'enable-compression' => \$enable_compression,
    'aws-iam-role:s' => \$aws_iam_role,
    );

}

# Prints out or logs an error and then exits.
sub exit_with_error
{
  my $message = shift;
  report_message(LOG_ERR, $message);
 
  if (!$from_cron) {
    print STDERR "\nFor more information, run 'mon-put-instance-data.pl --help'\n\n";
  }

  exit 1;
}

# Prints out or logs a message.
sub report_message
{
  my $log_level = shift;
  my $message = shift;
  chomp $message;
 
  if ($from_cron)
  {
    setlogsock('unix');
    openlog($client_name, 'nofatal', LOG_USER);
    syslog($log_level, $message);
    closelog;
  }
  elsif ($log_level == LOG_ERR) {
    print STDERR "\nERROR: $message\n";
  }
  elsif ($log_level == LOG_WARNING) {
    print "\nWARNING: $message\n";
  }
  elsif ($log_level == LOG_INFO) {
    print "\nINFO: $message\n";
  }
}

if (!$parse_result) {
  exit_with_error($parse_error);
}
if ($show_version) {
  print "\n$client_name version $version\n\n";
  exit 0;
}
if ($show_help || $argv_size < 1) {
  print $usage;
  exit 0;
}
if ($from_cron) {
  $verbose = 0;
}

# check for empty values in provided arguments
if (defined($aws_credential_file) && length($aws_credential_file) == 0) {
  exit_with_error("Path to AWS credential file is not provided.");
}
if (defined($aws_access_key_id) && length($aws_access_key_id) == 0) {
  exit_with_error("Value of AWS access key id is not specified.");
}
if (defined($aws_secret_key) && length($aws_secret_key) == 0) {
  exit_with_error("Value of AWS secret key is not specified.");
}
if (defined($mem_units) && length($mem_units) == 0) {
  exit_with_error("Value of memory units is not specified.");
}
if (defined($disk_units) && length($disk_units) == 0) {
  exit_with_error("Value of disk space units is not specified.");
}
if (defined($aws_iam_role) && length($aws_iam_role) == 0) {
  exit_with_error("Value of AWS IAM role is not specified.");
}

# check for inconsistency of provided arguments
if (defined($aws_credential_file) && defined($aws_access_key_id)) {
  exit_with_error("Do not provide AWS credential file and AWS access key id options together.");
}
elsif (defined($aws_credential_file) && defined($aws_secret_key)) {
  exit_with_error("Do not provide AWS credential file and AWS secret key options together.");
}
elsif (defined($aws_access_key_id) && !defined($aws_secret_key)) {
  exit_with_error("AWS secret key is not specified.");
}
elsif (!defined($aws_access_key_id) && defined($aws_secret_key)) {
  exit_with_error("AWS access key id is not specified.");
}
elsif (defined($aws_iam_role) && defined($aws_credential_file)) {
  exit_with_error("Do not provide AWS IAM role and AWS credential file options together.");
}
elsif (defined($aws_iam_role) && defined($aws_secret_key)) {
  exit_with_error("Do not provide AWS IAM role and AWS access key id/secret key options together.");
}

# decide on the reporting units for memory and swap usage
if (!defined($mem_units) || lc($mem_units) eq 'megabytes') {
  $mem_units = 'Megabytes';
  $mem_unit_div = MEGA;
}
elsif (lc($mem_units) eq 'bytes') {
  $mem_units = 'Bytes';
  $mem_unit_div = 1;
}
elsif (lc($mem_units) eq 'kilobytes') {
  $mem_units = 'Kilobytes';
  $mem_unit_div = KILO;
}
elsif (lc($mem_units) eq 'gigabytes') {
  $mem_units = 'Gigabytes';
  $mem_unit_div = GIGA;
}
else {
  exit_with_error("Unsupported memory units '$mem_units'. Use Bytes, Kilobytes, Megabytes, or Gigabytes.");
}

# decide on the reporting units for disk space usage
if (!defined($disk_units) || lc($disk_units) eq 'gigabytes') {
  $disk_units = 'Gigabytes';
  $disk_unit_div = GIGA;
}
elsif (lc($disk_units) eq 'bytes') {
  $disk_units = 'Bytes';
  $disk_unit_div = 1;
}
elsif (lc($disk_units) eq 'kilobytes') {
  $disk_units = 'Kilobytes';
  $disk_unit_div = KILO;
}
elsif (lc($disk_units) eq 'megabytes') {
  $disk_units = 'Megabytes';
  $disk_unit_div = MEGA;
}
else {
  exit_with_error("Unsupported disk space units '$disk_units'. Use Bytes, Kilobytes, Megabytes, or Gigabytes.");
}

my $df_path = '';
my $report_disk_space;
foreach my $path (@mount_path) {
  if (length($path) == 0) {
    exit_with_error("Value of disk path is not specified.");
  }
  elsif (-e $path) {
    $report_disk_space = 1;
    $df_path .= ' '.$path;
  }
  else {
    exit_with_error("Disk file path '$path' does not exist or cannot be accessed.");
  }
}

if ($report_disk_space && !$report_disk_util && !$report_disk_used && !$report_disk_avail) {
  exit_with_error("Disk path is provided but metrics to report disk space are not specified.");
}
if (!$report_disk_space && ($report_disk_util || $report_disk_used || $report_disk_avail)) {
  exit_with_error("Metrics to report disk space are provided but disk path is not specified.");
}

my $timestamp = CloudWatchClient::get_offset_time(NOW);
my $instance_id = CloudWatchClient::get_instance_id();

if (!defined($instance_id) || length($instance_id) == 0) {
  exit_with_error("Cannot obtain instance id from EC2 meta-data.");
}

if ($aggregated && lc($aggregated) ne 'only') {
  exit_with_error("Unrecognized value '$aggregated' for --aggregated option.");
}
if ($aggregated && lc($aggregated) eq 'only') {
  $aggregated = AGGREGATED_ONLY;
}
elsif (defined($aggregated)) {
  $aggregated = INCL_AGGREGATED;
}

my $image_id;
my $instance_type;
if ($aggregated) {
  $image_id = CloudWatchClient::get_image_id();
  $instance_type = CloudWatchClient::get_instance_type();
}

if ($auto_scaling && lc($auto_scaling) ne 'only') {
  exit_with_error("Unrecognized value '$auto_scaling' for --auto-scaling option.");
}
if ($auto_scaling && lc($auto_scaling) eq 'only') {
  $auto_scaling = AGGREGATED_ONLY;
}
elsif (defined($auto_scaling)) {
  $auto_scaling = INCL_AGGREGATED;
}

my $as_group_name;
if ($auto_scaling)
{
  my %opts = ();
  $opts{'aws-credential-file'} = $aws_credential_file;
  $opts{'aws-access-key-id'} = $aws_access_key_id;
  $opts{'aws-secret-key'} = $aws_secret_key;
  $opts{'verbose'} = $verbose;
  $opts{'verify'} = $verify;
  $opts{'user-agent'} = "$client_name/$version";
  $opts{'aws-iam-role'} = $aws_iam_role;
  
  my ($code, $reply) = CloudWatchClient::get_auto_scaling_group(\%opts);

  if ($code == 200) {
    $as_group_name = $reply;
  }
  else {
    report_message(LOG_WARNING, "Failed to call EC2 to obtain Auto Scaling group name. ".
      "HTTP Status Code: $code. Error Message: $reply");
  }

  if (!$as_group_name)
  {
    if (!$verify)
    {
      report_message(LOG_WARNING, "The Auto Scaling metrics will not be reported this time.");
      
      if ($auto_scaling == AGGREGATED_ONLY) {
        print("\n") if (!$from_cron);
        exit 0;
      }
    }
    else {
      $as_group_name = 'VerificationOnly';
    }
  }
}

my %params = ();
$params{'Input'} = {};
my $input_ref = $params{'Input'}; 
$input_ref->{'Namespace'} = "System/Linux";

#
# Adds a new metric to the request
#
sub add_single_metric
{
  my $name = shift;
  my $unit = shift;
  my $value = shift;
  my $dims = shift;
  
  my $metric = {};

  $metric->{"MetricName"} = $name;
  $metric->{"Timestamp"} = $timestamp;
  $metric->{"RawValue"} = $value;
  $metric->{"Unit"} = $unit;
  
  my $dimensions = [];
  foreach my $key (sort keys %$dims)
  {
    push(@$dimensions, {"Name" => $key, "Value" => $dims->{$key}});
  }
  
  $metric->{"Dimensions"} = $dimensions;  
  push(@{$input_ref->{'MetricData'}},  $metric);
  ++$mcount;
}

#
# Adds all metric variations for the specified metric name
#
sub add_metric
{
  my $name = shift;
  my $unit = shift;
  my $value = shift;
  my $filesystem = shift;
  my $mount = shift;
  
  $input_ref->{'MetricData'} = [] if !(exists $input_ref->{'MetricData'});
  
  my %dims = ();
  my %xdims = ();
  $xdims{'MountPath'} = $mount if $mount;
  $xdims{'Filesystem'} = $filesystem if $filesystem;
  
  my $auto_scaling_only = defined($auto_scaling) && $auto_scaling == AGGREGATED_ONLY;
  my $aggregated_only = defined($aggregated) && $aggregated == AGGREGATED_ONLY;
  
  if (!$auto_scaling_only && !$aggregated_only) {
    %dims = (('InstanceId' => $instance_id), %xdims);
    add_single_metric($name, $unit, $value, \%dims);
  }
  
  if ($as_group_name) {
    %dims = (('AutoScalingGroupName' => $as_group_name), %xdims);
    add_single_metric($name, $unit, $value, \%dims);
  }

  if ($instance_type) {
    %dims = (('InstanceType' => $instance_type), %xdims);
    add_single_metric($name, $unit, $value, \%dims);
  }

  if ($image_id) {
    %dims = (('ImageId' => $image_id), %xdims);
    add_single_metric($name, $unit, $value, \%dims);
  }

  if ($aggregated) {
    %dims = %xdims;
    add_single_metric($name, $unit, $value, \%dims);
  }

  print "$name [$mount]: $value ($unit)\n" if ($verbose && $mount);
  print "$name: $value ($unit)\n" if ($verbose && !$mount);
}

# avoid a storm of calls at the beginning of a minute
if ($from_cron) {
  sleep(rand(20));
}

# collect memory and swap metrics
my %meminfo;
foreach my $line (split('\n', `/bin/cat /proc/meminfo`)) {
  if($line =~ /^(.*?):\s+(\d+)/) {
    $meminfo{$1} = $2;
  }
}

# meminfo values are in kilobytes
my $mem_total = $meminfo{'MemTotal'} * KILO;
my $mem_free = $meminfo{'MemFree'} * KILO;
my $mem_used = $mem_total - $mem_free;

my $mem_util = 0;
$mem_util = 100 * $mem_used / $mem_total if ($mem_total > 0);

my $cpu_total = 0;
my $cpu_used = 0;
my $cpu_util = 0;

foreach my $line (split('\n', `/bin/cat /proc/stat`)) {
    if($cpu_total == 0 && $line =~ /^cpu +(\d+) \d+ (\d+) (\d+)/) {
        $cpu_used = $1 + $2;
        $cpu_total = $cpu_used + $3;
    }
}

$cpu_util = 100 * $cpu_used / $cpu_total if ($cpu_total > 0);

my $max_cpu_mem_util = $mem_util;
$max_cpu_mem_util = $cpu_util if($max_cpu_mem_util < $cpu_util);

add_metric('MemoryUtilization', 'Percent', $mem_util);
add_metric('CpuUtilization', 'Percent', $cpu_util);
add_metric('MaxUtilization', 'Percent', $max_cpu_mem_util);

# send metrics over to CloudWatch if any

if ($mcount > 0)
{
  my %opts = ();
  $opts{'aws-credential-file'} = $aws_credential_file;
  $opts{'aws-access-key-id'} = $aws_access_key_id;
  $opts{'aws-secret-key'} = $aws_secret_key;
  $opts{'retries'} = 2;
  $opts{'verbose'} = $verbose;
  $opts{'verify'} = $verify;
  $opts{'user-agent'} = "$client_name/$version";
  $opts{'enable_compression'} = 1 if ($enable_compression);
  $opts{'aws-iam-role'} = $aws_iam_role;
  
  my $response = CloudWatchClient::call_json('PutMetricData', \%params, \%opts);
  my $code = $response->code;
  my $message = $response->message;
  
  if ($code == 200 && !$from_cron) {
    if ($verify) {
      print "\nVerification completed successfully. No actual metrics sent to CloudWatch.\n\n";
    } else {
      my $request_id = $response->headers->{'x-amzn-requestid'};
      print "\nSuccessfully reported metrics to CloudWatch. Reference Id: $request_id\n\n";
    }
  }
  elsif ($code < 100) {
    exit_with_error($message);
  }
  elsif ($code != 200) {
    exit_with_error("Failed to call CloudWatch: HTTP $code. Message: $message");
  }
}
else {
  exit_with_error("No metrics prepared for submission to CloudWatch.");
}

exit 0;
