# Copyright (c) 2023, NVIDIA CORPORATION.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


"""Wrapper class to run tools associated with RAPIDS Accelerator for Apache Spark plugin on DATABRICKS_AWS."""
from spark_rapids_tools import CspEnv
from spark_rapids_pytools.cloud_api.sp_types import DeployMode
from spark_rapids_pytools.common.utilities import Utils, ToolLogging
from spark_rapids_pytools.rapids.diagnostic import Diagnostic
from spark_rapids_pytools.rapids.profiling import ProfilingAsLocal
from spark_rapids_pytools.rapids.qualification import QualFilterApp, QualificationAsLocal, QualGpuClusterReshapeType


class CliDBAWSLocalMode:  # pylint: disable=too-few-public-methods
    """
    A wrapper that runs the RAPIDS Accelerator tools locally on the dev machine for DATABRICKS_AWS.
    """

    @staticmethod
    def qualification(cpu_cluster: str = None,
                      eventlogs: str = None,
                      profile: str = None,
                      aws_profile: str = None,
                      local_folder: str = None,
                      remote_folder: str = None,
                      gpu_cluster: str = None,
                      tools_jar: str = None,
                      credentials_file: str = None,
                      filter_apps: str = QualFilterApp.tostring(QualFilterApp.SAVINGS),
                      gpu_cluster_recommendation: str = QualGpuClusterReshapeType.tostring(
                          QualGpuClusterReshapeType.get_default()),
                      jvm_heap_size: int = None,
                      verbose: bool = None,
                      cpu_discount: int = None,
                      gpu_discount: int = None,
                      global_discount: int = None,
                      **rapids_options) -> None:
        """
        The Qualification tool analyzes Spark events generated from CPU based Spark applications to
        help quantify the expected acceleration and costs savings of migrating a Spark application
        or query to GPU. The wrapper downloads dependencies and executes the analysis on the local
        dev machine.
        :param cpu_cluster: The Databricks-cluster on which the Spark applications were executed. The argument
                can be a Databricks-cluster ID or a valid path to the cluster's properties file (json format)
                generated by the databricks-CLI.
        :param  eventlogs: Event log filenames or S3 storage directories
                containing event logs (comma separated). If missing, the wrapper reads the Spark's
                property `spark.eventLog.dir` defined in `cpu_cluster`. This property should be included
                in the output of `databricks clusters get CLUSTER_ID [flags]`.
                Note that the wrapper will raise an exception if the property is not set.
        :param profile: A named Databricks profile to get the settings/credentials of the Databricks CLI.
        :param aws_profile: A named AWS profile to get the settings/credentials of the AWS account.
        :param local_folder: Local work-directory path to store the output and to be used as root
                directory for temporary folders/files. The final output will go into a subdirectory called
                ${local_folder}/qual-${EXEC_ID} where exec_id is an auto-generated unique identifier of the
                execution. If the argument is NONE, the default value is the env variable
                RAPIDS_USER_TOOLS_OUTPUT_DIRECTORY if any; or the current working directory.
        :param remote_folder: An S3 folder where the output is uploaded at the end of execution.
                If no value is provided, the output will be only available on local disk.
        :param gpu_cluster: The Databricks-cluster on which the Spark applications is planned to be migrated.
                The argument can be a Databricks-cluster ID or a valid path to the cluster's properties file
                (json format) generated by the databricks-CLI. If missing, the wrapper maps the databricks machine
                instances of the original cluster into databricks instances that support GPU acceleration.
        :param tools_jar: Path to a bundled jar including Rapids tool. The path is a local filesystem,
                or remote S3 url. If missing, the wrapper downloads the latest rapids-4-spark-tools_*.jar
                from maven repo.
        :param credentials_file: The local path of JSON file that contains the application credentials.
               If missing, the wrapper looks for "DATABRICKS_CONFIG_FILE" environment variable
               to provide the location of a credential file. The default credentials file exists as
               "~/.databrickscfg" on Unix, Linux, or macOS
        :param filter_apps: filtering criteria of the applications listed in the final STDOUT table
                is one of the following (ALL, SPEEDUPS, savings).
                Note that this filter does not affect the CSV report.
                "ALL" means no filter applied. "SPEEDUPS" lists all the apps that are either
                'Recommended', or 'Strongly Recommended' based on speedups. "SAVINGS"
                lists all the apps that have positive estimated GPU savings except for the apps that
                are "Not Applicable".
        :param gpu_cluster_recommendation: The type of GPU cluster recommendation to generate.
               It accepts one of the following ("CLUSTER", "JOB" and the default value "MATCH").
                "MATCH": keep GPU cluster same number of nodes as CPU cluster;
                "CLUSTER": recommend optimal GPU cluster by cost for entire cluster;
                "JOB": recommend optimal GPU cluster by cost per job.
        :param jvm_heap_size: The maximum heap size of the JVM in gigabytes.
        :param verbose: True or False to enable verbosity to the wrapper script.
        :param cpu_discount: A percent discount for the cpu cluster cost in the form of an integer value
                (e.g. 30 for 30% discount).
        :param gpu_discount: A percent discount for the gpu cluster cost in the form of an integer value
                (e.g. 30 for 30% discount).
        :param global_discount: A percent discount for both the cpu and gpu cluster costs in the form of an
                integer value (e.g. 30 for 30% discount).
        :param rapids_options: A list of valid Qualification tool options.
                Note that the wrapper ignores ["output-directory", "platform"] flags, and it does not support
                multiple "spark-property" arguments.
                For more details on Qualification tool options, please visit
                https://docs.nvidia.com/spark-rapids/user-guide/latest/spark-qualification-tool.html#qualification-tool-options
        """
        verbose = Utils.get_value_or_pop(verbose, rapids_options, 'v', False)
        profile = Utils.get_value_or_pop(profile, rapids_options, 'p')
        aws_profile = Utils.get_value_or_pop(aws_profile,  rapids_options, 'a')
        remote_folder = Utils.get_value_or_pop(remote_folder, rapids_options, 'r')
        jvm_heap_size = Utils.get_value_or_pop(jvm_heap_size, rapids_options, 'j', 24)
        eventlogs = Utils.get_value_or_pop(eventlogs, rapids_options, 'e')
        filter_apps = Utils.get_value_or_pop(filter_apps, rapids_options, 'f')
        tools_jar = Utils.get_value_or_pop(tools_jar, rapids_options, 't')
        local_folder = Utils.get_value_or_pop(local_folder, rapids_options, 'l')
        if verbose:
            # when debug is set to true set it in the environment.
            ToolLogging.enable_debug_mode()
        wrapper_qual_options = {
            'platformOpts': {
                # the databricks profile
                'profile': profile,
                'awsProfile': aws_profile,
                'credentialFile': credentials_file,
                'deployMode': DeployMode.LOCAL,
            },
            'migrationClustersProps': {
                'cpuCluster': cpu_cluster,
                'gpuCluster': gpu_cluster
            },
            'jobSubmissionProps': {
                'remoteFolder': remote_folder,
                'platformArgs': {
                    'jvmMaxHeapSize': jvm_heap_size
                }
            },
            'eventlogs': eventlogs,
            'filterApps': filter_apps,
            'toolsJar': tools_jar,
            'gpuClusterRecommendation': gpu_cluster_recommendation,
            'cpuDiscount': cpu_discount,
            'gpuDiscount': gpu_discount,
            'globalDiscount': global_discount
        }
        QualificationAsLocal(platform_type=CspEnv.DATABRICKS_AWS,
                             cluster=None,
                             output_folder=local_folder,
                             wrapper_options=wrapper_qual_options,
                             rapids_options=rapids_options).launch()

    @staticmethod
    def profiling(gpu_cluster: str = None,
                  worker_info: str = None,
                  eventlogs: str = None,
                  profile: str = None,
                  aws_profile: str = None,
                  local_folder: str = None,
                  remote_folder: str = None,
                  tools_jar: str = None,
                  credentials_file: str = None,
                  jvm_heap_size: int = None,
                  verbose: bool = None,
                  **rapids_options) -> None:
        """
        The Profiling tool analyzes both CPU or GPU generated event logs and generates information
        which can be used for debugging and profiling Apache Spark applications.

        :param  gpu_cluster: The Databricks-cluster on which the Spark applications were executed. The argument
                can be a Databricks-cluster ID or a valid path to the cluster's properties file (json format)
                generated by the databricks-CLI. If missing, then the argument worker_info has to be provided.
        :param  worker_info: A path pointing to a yaml file containing the system information of a
                worker node. It is assumed that all workers are homogenous.
                If missing, the wrapper pulls the worker info from the "gpu_cluster".
        :param  eventlogs: Event log filenames or S3 storage directories
                containing event logs (comma separated). If missing, the wrapper reads the Spark's
                property `spark.eventLog.dir` defined in `gpu_cluster`. This property should be included
                in the output of `databricks clusters get CLUSTER_ID [flags]`.
                Note that the wrapper will raise an exception if the property is not set.
        :param profile: A named Databricks profile to get the settings/credentials of the Databricks CLI.
        :param aws_profile: A named AWS profile to get the settings/credentials of the AWS account.
        :param local_folder: Local work-directory path to store the output and to be used as root
                directory for temporary folders/files. The final output will go into a subdirectory called
                ${local_folder}/prof-${EXEC_ID} where exec_id is an auto-generated unique identifier of the
                execution. If the argument is NONE, the default value is the env variable
                RAPIDS_USER_TOOLS_OUTPUT_DIRECTORY if any; or the current working directory.
        :param remote_folder: A S3 folder where the output is uploaded at the end of execution.
                If no value is provided, the output will be only available on local disk.
        :param tools_jar: Path to a bundled jar including Rapids tool. The path is a local filesystem,
                or remote S3 url. If missing, the wrapper downloads the latest rapids-4-spark-tools_*.jar
                from maven repo.
        :param credentials_file: The local path of JSON file that contains the application credentials.
               If missing, the wrapper looks for "DATABRICKS_CONFIG_FILE" environment variable
               to provide the location of a credential file. The default credentials file exists as
               "~/.databrickscfg" on Unix, Linux, or macOS.
        :param verbose: True or False to enable verbosity to the wrapper script.
        :param jvm_heap_size: The maximum heap size of the JVM in gigabytes.
        :param rapids_options: A list of valid Profiling tool options.
                Note that the wrapper ignores ["output-directory", "worker-info"] flags, and it does not support
                multiple "spark-property" arguments.
                For more details on Profiling tool options, please visit
                https://docs.nvidia.com/spark-rapids/user-guide/latest/spark-profiling-tool.html#profiling-tool-options
        """
        verbose = Utils.get_value_or_pop(verbose, rapids_options, 'v', False)
        profile = Utils.get_value_or_pop(profile, rapids_options, 'p')
        aws_profile = Utils.get_value_or_pop(aws_profile,  rapids_options, 'a')
        credentials_file = Utils.get_value_or_pop(credentials_file, rapids_options, 'c')
        gpu_cluster = Utils.get_value_or_pop(gpu_cluster, rapids_options, 'g')
        remote_folder = Utils.get_value_or_pop(remote_folder, rapids_options, 'r')
        jvm_heap_size = Utils.get_value_or_pop(jvm_heap_size, rapids_options, 'j', 24)
        eventlogs = Utils.get_value_or_pop(eventlogs, rapids_options, 'e')
        tools_jar = Utils.get_value_or_pop(tools_jar, rapids_options, 't')
        worker_info = Utils.get_value_or_pop(worker_info, rapids_options, 'w')
        local_folder = Utils.get_value_or_pop(local_folder, rapids_options, 'l')
        if verbose:
            # when debug is set to true set it in the environment.
            ToolLogging.enable_debug_mode()
        wrapper_prof_options = {
            'platformOpts': {
                # the databricks profile
                'profile': profile,
                'awsProfile': aws_profile,
                'credentialFile': credentials_file,
                'deployMode': DeployMode.LOCAL,
            },
            'migrationClustersProps': {
                'gpuCluster': gpu_cluster
            },
            'jobSubmissionProps': {
                'remoteFolder': remote_folder,
                'platformArgs': {
                    'jvmMaxHeapSize': jvm_heap_size
                }
            },
            'eventlogs': eventlogs,
            'toolsJar': tools_jar,
            'autoTunerFileInput': worker_info
        }
        ProfilingAsLocal(platform_type=CspEnv.DATABRICKS_AWS,
                         output_folder=local_folder,
                         wrapper_options=wrapper_prof_options,
                         rapids_options=rapids_options).launch()

    @staticmethod
    def diagnostic(cluster: str,
                   profile: str = None,
                   aws_profile: str = None,
                   output_folder: str = None,
                   credentials_file: str = None,
                   port: int = 2200,
                   key_file: str = None,
                   thread_num: int = 3,
                   yes: bool = False,
                   verbose: bool = False) -> None:
        """
        Diagnostic tool to collect information from Databricks cluster, such as OS version, # of worker nodes,
        Yarn configuration, Spark version and error logs etc. Please note, some sensitive information might
        be collected by this tool, e.g. access secret configured in configuration files or dumped to log files.
        :param cluster: ID of the Databricks cluster running an accelerated computing instance.
        :param profile: A named Databricks profile to get the settings/credentials of the Databricks CLI.
        :param aws_profile: A named AWS profile to get the settings/credentials of the AWS account.
        :param output_folder: Local path where the archived result will be saved.
               Note that this argument only accepts local filesystem. If the argument is NONE,
               the default value is the env variable "RAPIDS_USER_TOOLS_OUTPUT_DIRECTORY" if any;
               or the current working directory.
        :param credentials_file: The local path of JSON file that contains the application credentials.
               If missing, the wrapper looks for "DATABRICKS_CONFIG_FILE" environment variable
               to provide the location of a credential file. The default credentials file exists as
               "~/.databrickscfg" on Unix, Linux, or macOS.
        :param port: Port number to be used for the ssh connections.
        :param key_file: Path to the private key file to be used for the ssh connections.
        :param thread_num: Number of threads to access remote cluster nodes in parallel. The valid value
               is 1~10. The default value is 3.
        :param yes: auto confirm to interactive question.
        :param verbose: True or False to enable verbosity to the wrapper script.
        """
        if verbose:
            # when debug is set to true set it in the environment.
            ToolLogging.enable_debug_mode()
        wrapper_diag_options = {
            'platformOpts': {
                'profile': profile,
                'awsProfile': aws_profile,
                'credentialFile': credentials_file,
                'sshPort': port,
                'sshKeyFile': key_file,
            },
            'threadNum': thread_num,
            'yes': yes,
        }
        diag_tool = Diagnostic(platform_type=CspEnv.DATABRICKS_AWS,
                               cluster=cluster,
                               output_folder=output_folder,
                               wrapper_options=wrapper_diag_options)
        diag_tool.launch()


class DBAWSWrapper:  # pylint: disable=too-few-public-methods
    """
    A wrapper script to run RAPIDS Accelerator tools (Qualification, Profiling, and Diagnostic) on Databricks_AWS.
    """

    def __init__(self):
        self.qualification = CliDBAWSLocalMode.qualification
        self.profiling = CliDBAWSLocalMode.profiling
        self.diagnostic = CliDBAWSLocalMode.diagnostic
