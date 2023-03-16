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

import argparse
from pyspark import SparkContext        # pylint: disable=import-error
from pyspark.sql import SparkSession    # pylint: disable=import-error
from pyspark.sql.functions import col   # pylint: disable=import-error
import time

def validation(spark, args):

    if not valid_input(spark,args):
        print('|--Please Check The Inputs --|')
        return

    # valid PK(s) only in table1
    result = valid_pk_only_in_one_table(spark, args.format, args.t1, args.t2, args.t1p, args.t2p, args.pk, args.e, args.i, args.f, args.o, args.of)
    print(f'|--PK(s) only in {args.t1} :--|')
    print(result.show())
    # valid PK(s) only in table2
    result = valid_pk_only_in_one_table(spark, args.format, args.t2, args.t1, args.t1p, args.t2p, args.pk, args.e, args.i, args.f, args.o, args.of)
    print(f'|--PK(s) only in {args.t2} :--|')
    print(result.show())

    # valid result table with the same PK but different values for that column(s)
    # result = get_cols_diff_with_same_pk(spark, args.format, args.t1, args.t2, args.pk, args.t1p, args.f, args.i, args.e)
    # print("columns with same PK(s) but diff values : ")
    # print(result.show())
    #
    # start_time = time.time()
    print('------------run validation success-----')

def valid_input(spark, args):
    """
    Check the input is valida for matadata validation tool
    1- valid table
    2- valid included column
    3- check format supported
    """
    if not valid_table(spark, args):
        return False
    if not valid_metadata_included_column(spark, args):
        return False
    if args.format != 'hive':
        print('|--Currently only support hive format--|')
    return True

def valid_table(spark, args):
    """
    Check if the tables exist
    """
    if not spark._jsparkSession.catalog().tableExists(args.t1):
        print(f'|--Table {args.t1} does not exist!--|')
        return False
    if not spark._jsparkSession.catalog().tableExists(args.t2):
        print(f'|--Table {args.t2} does not exist!--|')
        return False
    return True

def valid_metadata_included_column(spark, args):
    """
    Check if the included column valid
    """
    if args.i in ['None', 'all']:
        return True
    table_DF = load_table(spark, args.format, args.t1, args.t1p, args.pk, args.e, args.i, args.f, "")
    excluded_columns_list = [e.strip() for e in args.e.split(",")]
    verify_column = [i.strip() for i in args.i.split(",") if i not in excluded_columns_list]
    verify_DF = table_DF.select(verify_column)

    for c in verify_DF.schema.fields:
        # here only excluded 'date' because it will raise exception, we also should excluded str/map/nested
        if(any(fnmatch.fnmatch(c.dataType.simpleString(), pattern) for pattern in
                            ['*date*'])):
            print(f'|--Unsupported metadata included data type: {c.dataType.simpleString()} for column: {c}--|')
            return False
    return True

# def row_counts(spark, format, table, t1p, t1f):
#     """Get the row counts of a table according"""
#     sql = "select count(*) from table"
#     where_clause = ""
#     if t1p != 'None' and t1f !='None':
#         where_clause = f" where {t1p} and {t1f}"
#     elif t1p != 'None':
#         where_clause = f" where {t1p}"
#     elif t1f != 'None':
#         where_clause = f" where {t1f}"
#     if format in ['parquet', 'orc', 'csv']:
#         path = table
#         spark.read.format(format).load(path).createOrReplaceTempView("table")
#         sql += where_clause
#
#         result = spark.sql(sql)
#         return result
#     elif format == "hive":
#         print("----todo---hive--")
#         return 0

def valid_pk_only_in_one_table(spark, format, t1, t2, t1p, t2p, pk, e, i, f, o, of):
    """valid PK(s) only in one table"""
    if format in ['parquet', 'orc', 'csv']:

        # load table1
        load_table(spark, format, t1, t1p, pk, e, i, f, "table1")
        # load table2
        load_table(spark, format, t2, t2p, pk, e, i, f, "table2")

        sql = f"select {pk} from table1 except select {pk} from table2"
        result = spark.sql(sql)
        return result

    elif format == "hive":
        sql = f"select {pk} from {t1} except select {pk} from {t2}"
        where_clause = ""
        if any(cond is not None for cond in [t1p,t2p,f]):
            where_clause = ' where ' + ' and '.join(x for x in [t1p, t2p, f] if x is not None and x != 'None')

        sql += where_clause
        print('-----yuadebug---')
        print(sql)
        result = spark.sql(sql)
        return result

    return

def get_cols_diff_with_same_pk(spark, format, table1_name, table2_name, pk, partitions, filter, included_columns, excluded_columns):
    if format in ['parquet', 'orc', 'csv']:
        pk_list = [i.strip() for i in pk.split(",")]
        included_columns_list = [i.strip() for i in included_columns.split(",")]
        excluded_columns_list = [e.strip() for e in excluded_columns.split(",")]
        select_columns = [f't1.{p}' for p in pk.split(',')] + [f't1.{c} as t1_{c}, t2.{c} as t2_{c}' for c in included_columns_list if
                                                               c not in excluded_columns_list]
        sql = f"""
                    SELECT {', '.join(select_columns)}
                    FROM table1 t1
                    FULL OUTER JOIN table2 t2 ON {' AND '.join([f't1.{c} = t2.{c}' for c in pk_list])}
                    WHERE ({' or '.join([f't1.{c} <> t2.{c}' for c in included_columns_list if c not in excluded_columns_list])} )
                """
        if partitions != 'None':
            partitions = [p.strip() for p in partitions.split("and")]
            sql += ' AND ( ' + ' AND '.join([f't1.{p} ' for p in partitions]) + ' )'

        if filter != 'None':
            filters = [f.strip() for f in filter.split("and")]
            sql += ' AND ( ' + ' AND '.join([f't1.{f} ' for f in filters]) + ' )'

        # Execute the query and return the result
        result = spark.sql(sql)

        return result
    elif format == "hive":
        print("----todo---hive-load_table-")

def load_table(spark, format, t1, t1p, pk, e, i, f, view_name):
    if format in ['parquet', 'orc', 'csv']:
        # select column clause
        cols = '*' if i is None else i
        # cols = cols if e is None else cols + f", EXCEPT ({e}) "
        sql = f"select {pk},{cols} from {view_name}"
        # where clause
        where_clause = ""
        path = t1
        if t1p != 'None' and f != 'None':
            where_clause = f" where {t1p} and {f}"
        elif t1p != 'None':
            where_clause = f" where {t1p}"
            # partition clause should be in real order as data path
            # path += partition_to_path(t1p)
        elif f != 'None':
            where_clause = f" where {f}"

        spark.read.format(format).load(path).createOrReplaceTempView(view_name)
        sql += where_clause
        result = spark.sql(sql)
        # result1 = spark.sql(sql1)
        # print(result)
        print(result)
    elif format == "hive":
        print("----todo---hive-load_table-")

def partition_to_path(partition_str, path):
    partition = {}
    if partition_str:
        partition_items = partition_str.split("and")
        partition = dict(item.split("=") for item in partition_items)
    partition_path = "/".join([f"{col}={val}" for col, val in partition.items()])
    return f"{path}/{partition_path}".replace(" ", "")


if __name__ == '__main__':

    parser = argparse.ArgumentParser()
    parser.add_argument('--format',
                        type=str,
                        help='The format of tables')
    parser.add_argument('--t1',
                        type=str,
                        help='table1')
    parser.add_argument('--t2',
                        type=str,
                        help='table2')
    parser.add_argument('--t1p',
                        type=str,
                        help='table1 partition')
    parser.add_argument('--t2p',
                        type=str,
                        help='table2 partition')
    parser.add_argument('--pk',
                        type=str,
                        help='primary key')
    parser.add_argument('--e',
                        type=str,
                        help='Exclude column option')
    parser.add_argument('--i',
                        type=str,
                        help='Include column option')
    parser.add_argument('--f',
                        type=str,
                        help='Condition to filter rows')
    parser.add_argument('--o',
                        type=str,
                        help='Output directory')
    parser.add_argument('--of',
                        type=str,
                        help='Output format, default is parquet')
    parser.add_argument('--p',
                        type=int,
                        help='Precision, default is 4')
    args = parser.parse_args()

    sc = SparkContext(appName='data-validation')
    spark = SparkSession(sc)

    validation(spark, args)

