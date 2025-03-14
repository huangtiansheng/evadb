# coding=utf-8
# Copyright 2018-2023 EvaDB
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
import json
import unittest
from pathlib import Path

from evadb.catalog.catalog_type import ColumnType, NdArrayType, VectorStoreType
from evadb.expression.abstract_expression import ExpressionType
from evadb.expression.comparison_expression import ComparisonExpression
from evadb.expression.constant_value_expression import ConstantValueExpression
from evadb.expression.function_expression import FunctionExpression
from evadb.expression.logical_expression import LogicalExpression
from evadb.expression.tuple_value_expression import TupleValueExpression
from evadb.parser.alias import Alias
from evadb.parser.create_function_statement import CreateFunctionStatement
from evadb.parser.create_index_statement import CreateIndexStatement
from evadb.parser.create_statement import (
    ColConstraintInfo,
    ColumnDefinition,
    CreateTableStatement,
)
from evadb.parser.delete_statement import DeleteTableStatement
from evadb.parser.drop_object_statement import DropObjectStatement
from evadb.parser.insert_statement import InsertTableStatement
from evadb.parser.load_statement import LoadDataStatement
from evadb.parser.parser import Parser
from evadb.parser.rename_statement import RenameTableStatement
from evadb.parser.select_statement import SelectStatement
from evadb.parser.set_statement import SetStatement
from evadb.parser.show_statement import ShowStatement
from evadb.parser.statement import AbstractStatement, StatementType
from evadb.parser.table_ref import JoinNode, TableInfo, TableRef, TableValuedExpression
from evadb.parser.types import (
    FileFormatType,
    JoinType,
    ObjectType,
    ParserOrderBySortType,
    ShowType,
)
from evadb.parser.use_statement import UseStatement


class ParserTests(unittest.TestCase):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def test_select_from_data_source(self):
        parser = Parser()

        query = "SELECT * FROM DemoDB.DemoTable"
        evadb_stmt_list = parser.parse(query)

        # check stmt itself
        self.assertIsInstance(evadb_stmt_list, list)
        self.assertEqual(len(evadb_stmt_list), 1)
        self.assertEqual(evadb_stmt_list[0].stmt_type, StatementType.SELECT)

        # from_table
        select_stmt = evadb_stmt_list[0]
        self.assertIsNotNone(select_stmt.from_table)
        self.assertIsInstance(select_stmt.from_table, TableRef)
        self.assertEqual(select_stmt.from_table.table.table_name, "DemoTable")
        self.assertEqual(select_stmt.from_table.table.database_name, "DemoDB")

    def test_use_statement(self):
        parser = Parser()

        query_list = [
            "SELECT * FROM DemoTable",
            """SELECT * FROM DemoTable WHERE col == "xxx"
            """,
            """SELECT * FROM DemoTable WHERE col == 'xxx'
            """,
        ]

        for query in query_list:
            use_query = f"USE DemoDB {{{query}}};"
            evadb_stmt_list = parser.parse(use_query)

            # check stmt itself
            self.assertIsInstance(evadb_stmt_list, list)
            self.assertEqual(len(evadb_stmt_list), 1)
            self.assertEqual(evadb_stmt_list[0].stmt_type, StatementType.USE)

            expected_stmt = UseStatement("DemoDB", query)
            actual_stmt = evadb_stmt_list[0]
            self.assertEqual(actual_stmt, expected_stmt)

    def test_create_index_statement(self):
        parser = Parser()

        create_index_query = "CREATE INDEX testindex ON MyVideo (featCol) USING FAISS;"
        evadb_stmt_list = parser.parse(create_index_query)

        # check stmt itself
        self.assertIsInstance(evadb_stmt_list, list)
        self.assertEqual(len(evadb_stmt_list), 1)
        self.assertEqual(evadb_stmt_list[0].stmt_type, StatementType.CREATE_INDEX)

        expected_stmt = CreateIndexStatement(
            "testindex",
            False,
            TableRef(TableInfo("MyVideo")),
            [
                ColumnDefinition("featCol", None, None, None),
            ],
            VectorStoreType.FAISS,
            [TupleValueExpression(name="featCol")],
        )
        actual_stmt = evadb_stmt_list[0]
        self.assertEqual(actual_stmt, expected_stmt)
        self.assertEqual(actual_stmt.index_def, create_index_query)

        # create if_not_exists
        expected_stmt = CreateIndexStatement(
            "testindex",
            True,
            TableRef(TableInfo("MyVideo")),
            [
                ColumnDefinition("featCol", None, None, None),
            ],
            VectorStoreType.FAISS,
            [TupleValueExpression(name="featCol")],
        )
        create_index_query = (
            "CREATE INDEX IF NOT EXISTS testindex ON MyVideo (featCol) USING FAISS;"
        )
        evadb_stmt_list = parser.parse(create_index_query)
        actual_stmt = evadb_stmt_list[0]
        expected_stmt._if_not_exists = True
        self.assertEqual(actual_stmt, expected_stmt)
        self.assertEqual(actual_stmt.index_def, create_index_query)

        # create index on Function expression
        create_index_query = (
            "CREATE INDEX testindex ON MyVideo (FeatureExtractor(featCol)) USING FAISS;"
        )
        evadb_stmt_list = parser.parse(create_index_query)

        # check stmt itself
        self.assertIsInstance(evadb_stmt_list, list)
        self.assertEqual(len(evadb_stmt_list), 1)
        self.assertEqual(evadb_stmt_list[0].stmt_type, StatementType.CREATE_INDEX)

        func_expr = FunctionExpression(None, "FeatureExtractor")
        func_expr.append_child(TupleValueExpression("featCol"))
        expected_stmt = CreateIndexStatement(
            "testindex",
            False,
            TableRef(TableInfo("MyVideo")),
            [
                ColumnDefinition("featCol", None, None, None),
            ],
            VectorStoreType.FAISS,
            [func_expr],
        )
        actual_stmt = evadb_stmt_list[0]
        self.assertEqual(actual_stmt, expected_stmt)
        self.assertEqual(actual_stmt.index_def, create_index_query)

    @unittest.skip("Skip parser exception handling testcase, moved to binder")
    def test_create_index_exception_statement(self):
        parser = Parser()

        create_index_query = (
            "CREATE INDEX testindex USING FAISS ON MyVideo (featCol1, featCol2);"
        )

        with self.assertRaises(Exception):
            parser.parse(create_index_query)

    def test_explain_dml_statement(self):
        parser = Parser()

        explain_query = "EXPLAIN SELECT CLASS FROM TAIPAI;"
        evadb_statement_list = parser.parse(explain_query)

        # check explain stmt itself
        self.assertIsInstance(evadb_statement_list, list)
        self.assertEqual(len(evadb_statement_list), 1)
        self.assertEqual(evadb_statement_list[0].stmt_type, StatementType.EXPLAIN)

        # check inner stmt
        inner_stmt = evadb_statement_list[0].explainable_stmt
        self.assertEqual(inner_stmt.stmt_type, StatementType.SELECT)

        # check inner stmt from
        self.assertIsNotNone(inner_stmt.from_table)
        self.assertIsInstance(inner_stmt.from_table, TableRef)
        self.assertEqual(inner_stmt.from_table.table.table_name, "TAIPAI")

    def test_explain_ddl_statement(self):
        parser = Parser()

        select_query = """SELECT id, Yolo(frame).labels FROM MyVideo
                        WHERE id<5; """
        explain_query = "EXPLAIN CREATE TABLE uadtrac_fastRCNN AS {}".format(
            select_query
        )

        evadb_statement_list = parser.parse(explain_query)

        # check explain stmt itself
        self.assertIsInstance(evadb_statement_list, list)
        self.assertEqual(len(evadb_statement_list), 1)
        self.assertEqual(evadb_statement_list[0].stmt_type, StatementType.EXPLAIN)

        # check inner stmt
        inner_stmt = evadb_statement_list[0].explainable_stmt
        self.assertEqual(inner_stmt.stmt_type, StatementType.CREATE)

        # check inner stmt from
        self.assertIsNotNone(
            inner_stmt.table_info, TableRef(TableInfo("uadetrac_fastRCNN"))
        )

    def test_create_table_statement(self):
        parser = Parser()

        single_queries = []
        single_queries.append(
            """CREATE TABLE IF NOT EXISTS Persons (
                  Frame_ID INTEGER UNIQUE,
                  Frame_Data TEXT,
                  Frame_Value FLOAT,
                  Frame_Array NDARRAY UINT8(5, 100, 2432, 4324, 100)
            );"""
        )

        expected_cci = ColConstraintInfo()
        expected_cci.nullable = True
        unique_cci = ColConstraintInfo()
        unique_cci.unique = True
        unique_cci.nullable = False
        expected_stmt = CreateTableStatement(
            TableInfo("Persons"),
            True,
            [
                ColumnDefinition("Frame_ID", ColumnType.INTEGER, None, (), unique_cci),
                ColumnDefinition("Frame_Data", ColumnType.TEXT, None, (), expected_cci),
                ColumnDefinition(
                    "Frame_Value", ColumnType.FLOAT, None, (), expected_cci
                ),
                ColumnDefinition(
                    "Frame_Array",
                    ColumnType.NDARRAY,
                    NdArrayType.UINT8,
                    (5, 100, 2432, 4324, 100),
                    expected_cci,
                ),
            ],
        )

        for query in single_queries:
            evadb_statement_list = parser.parse(query)
            self.assertIsInstance(evadb_statement_list, list)
            self.assertEqual(len(evadb_statement_list), 1)
            self.assertIsInstance(evadb_statement_list[0], AbstractStatement)
            self.assertEqual(evadb_statement_list[0], expected_stmt)

    def test_create_table_with_dimension_statement(self):
        # The test is for backwards compatibility
        parser = Parser()

        single_queries = []
        single_queries.append(
            """CREATE TABLE IF NOT EXISTS Persons (
                  Frame_ID INTEGER UNIQUE,
                  Frame_Data TEXT(10),
                  Frame_Value FLOAT(1000, 201),
                  Frame_Array NDARRAY UINT8(5, 100, 2432, 4324, 100)
            );"""
        )

        expected_cci = ColConstraintInfo()
        expected_cci.nullable = True
        unique_cci = ColConstraintInfo()
        unique_cci.unique = True
        unique_cci.nullable = False
        expected_stmt = CreateTableStatement(
            TableInfo("Persons"),
            True,
            [
                ColumnDefinition("Frame_ID", ColumnType.INTEGER, None, (), unique_cci),
                ColumnDefinition(
                    "Frame_Data", ColumnType.TEXT, None, (10,), expected_cci
                ),
                ColumnDefinition(
                    "Frame_Value", ColumnType.FLOAT, None, (1000, 201), expected_cci
                ),
                ColumnDefinition(
                    "Frame_Array",
                    ColumnType.NDARRAY,
                    NdArrayType.UINT8,
                    (5, 100, 2432, 4324, 100),
                    expected_cci,
                ),
            ],
        )

        for query in single_queries:
            evadb_statement_list = parser.parse(query)
            self.assertIsInstance(evadb_statement_list, list)
            self.assertEqual(len(evadb_statement_list), 1)
            self.assertIsInstance(evadb_statement_list[0], AbstractStatement)
            self.assertEqual(evadb_statement_list[0], expected_stmt)

    def test_create_table_statement_with_rare_datatypes(self):
        parser = Parser()
        query = """CREATE TABLE IF NOT EXISTS Dummy (
                  C NDARRAY UINT8(5),
                  D NDARRAY INT16(5),
                  E NDARRAY INT32(5),
                  F NDARRAY INT64(5),
                  G NDARRAY UNICODE(5),
                  H NDARRAY BOOLEAN(5),
                  I NDARRAY FLOAT64(5),
                  J NDARRAY DECIMAL(5),
                  K NDARRAY DATETIME(5)
            );"""

        evadb_statement_list = parser.parse(query)
        self.assertIsInstance(evadb_statement_list, list)
        self.assertEqual(len(evadb_statement_list), 1)
        self.assertIsInstance(evadb_statement_list[0], AbstractStatement)

    def test_create_table_statement_without_proper_datatype(self):
        parser = Parser()
        query = """CREATE TABLE IF NOT EXISTS Dummy (
                  C NDARRAY INT(5)
                );"""

        with self.assertRaises(Exception):
            parser.parse(query)

    def test_create_table_exception_statement(self):
        parser = Parser()

        create_table_query = "CREATE TABLE ();"

        with self.assertRaises(Exception):
            parser.parse(create_table_query)

    def test_rename_table_statement(self):
        parser = Parser()
        rename_queries = "RENAME TABLE student TO student_info"
        expected_stmt = RenameTableStatement(
            TableRef(TableInfo("student")), TableInfo("student_info")
        )
        evadb_statement_list = parser.parse(rename_queries)
        self.assertIsInstance(evadb_statement_list, list)
        self.assertEqual(len(evadb_statement_list), 1)
        self.assertEqual(evadb_statement_list[0].stmt_type, StatementType.RENAME)

        rename_stmt = evadb_statement_list[0]
        self.assertEqual(rename_stmt, expected_stmt)

    def test_drop_table_statement(self):
        parser = Parser()
        drop_queries = "DROP TABLE student_info"
        expected_stmt = DropObjectStatement(ObjectType.TABLE, "student_info", False)
        evadb_statement_list = parser.parse(drop_queries)
        self.assertIsInstance(evadb_statement_list, list)
        self.assertEqual(len(evadb_statement_list), 1)
        self.assertEqual(evadb_statement_list[0].stmt_type, StatementType.DROP_OBJECT)
        drop_stmt = evadb_statement_list[0]
        self.assertEqual(drop_stmt, expected_stmt)

    def test_drop_function_statement_str(self):
        drop_func_query1 = """DROP FUNCTION MyFunc;"""
        drop_func_query2 = """DROP FUNCTION IF EXISTS MyFunc;"""
        expected_stmt1 = DropObjectStatement(ObjectType.FUNCTION, "MyFunc", False)
        expected_stmt2 = DropObjectStatement(ObjectType.FUNCTION, "MyFunc", True)
        self.assertEqual(str(expected_stmt1), drop_func_query1)
        self.assertEqual(str(expected_stmt2), drop_func_query2)

    def test_single_statement_queries(self):
        parser = Parser()

        single_queries = []
        single_queries.append("SELECT CLASS FROM TAIPAI;")
        single_queries.append("SELECT CLASS FROM TAIPAI WHERE CLASS = 'VAN';")
        single_queries.append(
            "SELECT CLASS,REDNESS FROM TAIPAI \
            WHERE CLASS = 'VAN' AND REDNESS > 20.5;"
        )
        single_queries.append(
            "SELECT CLASS FROM TAIPAI \
            WHERE (CLASS = 'VAN' AND REDNESS < 300 ) OR REDNESS > 500;"
        )
        single_queries.append(
            "SELECT CLASS FROM TAIPAI \
            WHERE (CLASS = 'VAN' AND REDNESS < 300 ) OR REDNESS > 500;"
        )

        for query in single_queries:
            evadb_statement_list = parser.parse(query)

            self.assertIsInstance(evadb_statement_list, list)
            self.assertEqual(len(evadb_statement_list), 1)
            self.assertIsInstance(evadb_statement_list[0], AbstractStatement)

    def test_multiple_statement_queries(self):
        parser = Parser()

        multiple_queries = []
        multiple_queries.append(
            "SELECT CLASS FROM TAIPAI \
                WHERE (CLASS != 'VAN' AND REDNESS < 300)  OR REDNESS > 500; \
                SELECT REDNESS FROM TAIPAI \
                WHERE (CLASS = 'VAN' AND REDNESS = 300)"
        )

        for query in multiple_queries:
            evadb_statement_list = parser.parse(query)
            self.assertIsInstance(evadb_statement_list, list)
            self.assertEqual(len(evadb_statement_list), 2)
            self.assertIsInstance(evadb_statement_list[0], AbstractStatement)
            self.assertIsInstance(evadb_statement_list[1], AbstractStatement)

    def test_select_statement(self):
        parser = Parser()
        select_query = "SELECT CLASS, REDNESS FROM TAIPAI \
                WHERE (CLASS = 'VAN' AND REDNESS < 300 ) OR REDNESS > 500;"
        evadb_statement_list = parser.parse(select_query)
        self.assertIsInstance(evadb_statement_list, list)
        self.assertEqual(len(evadb_statement_list), 1)
        self.assertEqual(evadb_statement_list[0].stmt_type, StatementType.SELECT)

        select_stmt = evadb_statement_list[0]

        # target List
        self.assertIsNotNone(select_stmt.target_list)
        self.assertEqual(len(select_stmt.target_list), 2)
        self.assertEqual(select_stmt.target_list[0].etype, ExpressionType.TUPLE_VALUE)
        self.assertEqual(select_stmt.target_list[1].etype, ExpressionType.TUPLE_VALUE)

        # from_table
        self.assertIsNotNone(select_stmt.from_table)
        self.assertIsInstance(select_stmt.from_table, TableRef)
        self.assertEqual(select_stmt.from_table.table.table_name, "TAIPAI")

        # where_clause
        self.assertIsNotNone(select_stmt.where_clause)
        # other tests should go in expression testing

    def test_select_with_empty_string_literal(self):
        parser = Parser()

        select_query = """SELECT '' FROM TAIPAI;"""

        evadb_statement_list = parser.parse(select_query)
        self.assertIsInstance(evadb_statement_list, list)
        self.assertEqual(len(evadb_statement_list), 1)
        self.assertEqual(evadb_statement_list[0].stmt_type, StatementType.SELECT)

    def test_string_literal_with_escaped_single_quote(self):
        parser = Parser()

        select_query = """SELECT ChatGPT('Here\\'s a question', 'This is the context') FROM TAIPAI;"""

        evadb_statement_list = parser.parse(select_query)
        self.assertIsInstance(evadb_statement_list, list)
        self.assertEqual(len(evadb_statement_list), 1)
        self.assertEqual(evadb_statement_list[0].stmt_type, StatementType.SELECT)

    def test_string_literal_with_semi_colon(self):
        parser = Parser()

        select_query = """SELECT ChatGPT("Here's a; question", "This is the context") FROM TAIPAI;"""

        evadb_statement_list = parser.parse(select_query)
        self.assertIsInstance(evadb_statement_list, list)
        self.assertEqual(len(evadb_statement_list), 1)
        self.assertEqual(evadb_statement_list[0].stmt_type, StatementType.SELECT)

    def test_string_literal_with_single_quotes_from_variable(self):
        parser = Parser()

        question = json.dumps("Here's a question")
        answer = json.dumps('This is "the" context')

        select_query = f"""SELECT ChatGPT({question}, {answer}) FROM TAIPAI;"""

        evadb_statement_list = parser.parse(select_query)
        self.assertIsInstance(evadb_statement_list, list)
        self.assertEqual(len(evadb_statement_list), 1)
        self.assertEqual(evadb_statement_list[0].stmt_type, StatementType.SELECT)

    def test_select_union_statement(self):
        parser = Parser()
        select_union_query = "SELECT CLASS, REDNESS FROM TAIPAI \
            UNION ALL SELECT CLASS, REDNESS FROM SHANGHAI;"
        evadb_statement_list = parser.parse(select_union_query)
        select_stmt = evadb_statement_list[0]
        self.assertIsNotNone(select_stmt.union_link)
        self.assertEqual(select_stmt.union_all, True)
        second_select_stmt = select_stmt.union_link
        self.assertIsNone(second_select_stmt.union_link)

    def test_select_statement_class(self):
        """Testing setting different clauses for Select
        Statement class
        Class: SelectStatement"""

        select_stmt_new = SelectStatement()
        parser = Parser()

        select_query_new = "SELECT CLASS, REDNESS FROM TAIPAI \
            WHERE (CLASS = 'VAN' AND REDNESS < 400 ) OR REDNESS > 700;"
        evadb_statement_list = parser.parse(select_query_new)
        select_stmt = evadb_statement_list[0]

        select_stmt_new.where_clause = select_stmt.where_clause
        select_stmt_new.target_list = select_stmt.target_list
        select_stmt_new.from_table = select_stmt.from_table

        self.assertEqual(select_stmt_new.where_clause, select_stmt.where_clause)
        self.assertEqual(select_stmt_new.target_list, select_stmt.target_list)
        self.assertEqual(select_stmt_new.from_table, select_stmt.from_table)
        self.assertEqual(str(select_stmt_new), str(select_stmt))

    def test_select_statement_where_class(self):
        """
        Unit test for logical operators in the where clause.
        """

        def _verify_select_statement(evadb_statement_list):
            self.assertIsInstance(evadb_statement_list, list)
            self.assertEqual(len(evadb_statement_list), 1)
            self.assertEqual(evadb_statement_list[0].stmt_type, StatementType.SELECT)

            select_stmt = evadb_statement_list[0]

            # target list
            self.assertIsNotNone(select_stmt.target_list)
            self.assertEqual(len(select_stmt.target_list), 2)
            self.assertEqual(
                select_stmt.target_list[0].etype, ExpressionType.TUPLE_VALUE
            )
            self.assertEqual(select_stmt.target_list[0].name, "CLASS")
            self.assertEqual(
                select_stmt.target_list[1].etype, ExpressionType.TUPLE_VALUE
            )
            self.assertEqual(select_stmt.target_list[1].name, "REDNESS")

            # from table
            self.assertIsNotNone(select_stmt.from_table)
            self.assertIsInstance(select_stmt.from_table, TableRef)
            self.assertEqual(select_stmt.from_table.table.table_name, "TAIPAI")

            # where clause
            self.assertIsNotNone(select_stmt.where_clause)
            self.assertIsInstance(select_stmt.where_clause, LogicalExpression)
            self.assertEqual(select_stmt.where_clause.etype, ExpressionType.LOGICAL_AND)
            self.assertEqual(len(select_stmt.where_clause.children), 2)
            left = select_stmt.where_clause.children[0]
            right = select_stmt.where_clause.children[1]
            self.assertEqual(left.etype, ExpressionType.COMPARE_EQUAL)
            self.assertEqual(right.etype, ExpressionType.COMPARE_LESSER)

            self.assertEqual(len(left.children), 2)
            self.assertEqual(left.children[0].etype, ExpressionType.TUPLE_VALUE)
            self.assertEqual(left.children[0].name, "CLASS")
            self.assertEqual(left.children[1].etype, ExpressionType.CONSTANT_VALUE)
            self.assertEqual(left.children[1].value, "VAN")

            self.assertEqual(len(right.children), 2)
            self.assertEqual(right.children[0].etype, ExpressionType.TUPLE_VALUE)
            self.assertEqual(right.children[0].name, "REDNESS")
            self.assertEqual(right.children[1].etype, ExpressionType.CONSTANT_VALUE)
            self.assertEqual(right.children[1].value, 400)

        parser = Parser()
        select_query = (
            "SELECT CLASS, REDNESS FROM TAIPAI WHERE CLASS = 'VAN' AND REDNESS < 400;"
        )
        _verify_select_statement(parser.parse(select_query))

        # Case insensitive test
        select_query = (
            "select CLASS, REDNESS from TAIPAI where CLASS = 'VAN' and REDNESS < 400;"
        )
        _verify_select_statement(parser.parse(select_query))

        # Unsupported logical operator
        select_query = (
            "SELECT CLASS, REDNESS FROM TAIPAI WHERE CLASS = 'VAN' XOR REDNESS < 400;"
        )
        with self.assertRaises(NotImplementedError) as cm:
            parser.parse(select_query)
        self.assertEqual(str(cm.exception), "Unsupported logical operator: XOR")

    def test_select_statement_groupby_class(self):
        """Testing sample frequency"""

        parser = Parser()

        select_query = "SELECT FIRST(id) FROM TAIPAI GROUP BY '8 frames';"

        evadb_statement_list = parser.parse(select_query)
        self.assertIsInstance(evadb_statement_list, list)
        self.assertEqual(len(evadb_statement_list), 1)
        self.assertEqual(evadb_statement_list[0].stmt_type, StatementType.SELECT)

        select_stmt = evadb_statement_list[0]

        # target List
        self.assertIsNotNone(select_stmt.target_list)
        self.assertEqual(len(select_stmt.target_list), 1)
        self.assertEqual(
            select_stmt.target_list[0].etype, ExpressionType.AGGREGATION_FIRST
        )

        # from_table
        self.assertIsNotNone(select_stmt.from_table)
        self.assertIsInstance(select_stmt.from_table, TableRef)
        self.assertEqual(select_stmt.from_table.table.table_name, "TAIPAI")

        # sample_freq
        self.assertEqual(
            select_stmt.groupby_clause,
            ConstantValueExpression("8 frames", v_type=ColumnType.TEXT),
        )

    def test_select_statement_orderby_class(self):
        """Testing order by clause in select statement
        Class: SelectStatement"""

        parser = Parser()

        select_query = "SELECT CLASS, REDNESS FROM TAIPAI \
                    WHERE (CLASS = 'VAN' AND REDNESS < 400 ) OR REDNESS > 700 \
                    ORDER BY CLASS, REDNESS DESC;"
        # if orderby sort_type (ASC/DESC) not provided, should default to ASC

        evadb_statement_list = parser.parse(select_query)
        self.assertIsInstance(evadb_statement_list, list)
        self.assertEqual(len(evadb_statement_list), 1)
        self.assertEqual(evadb_statement_list[0].stmt_type, StatementType.SELECT)

        select_stmt = evadb_statement_list[0]

        # target List
        self.assertIsNotNone(select_stmt.target_list)
        self.assertEqual(len(select_stmt.target_list), 2)
        self.assertEqual(select_stmt.target_list[0].etype, ExpressionType.TUPLE_VALUE)
        self.assertEqual(select_stmt.target_list[1].etype, ExpressionType.TUPLE_VALUE)

        # from_table
        self.assertIsNotNone(select_stmt.from_table)
        self.assertIsInstance(select_stmt.from_table, TableRef)
        self.assertEqual(select_stmt.from_table.table.table_name, "TAIPAI")

        # where_clause
        self.assertIsNotNone(select_stmt.where_clause)

        # orderby_clause
        self.assertIsNotNone(select_stmt.orderby_list)
        self.assertEqual(len(select_stmt.orderby_list), 2)
        self.assertEqual(select_stmt.orderby_list[0][0].name, "CLASS")
        self.assertEqual(select_stmt.orderby_list[0][1], ParserOrderBySortType.ASC)
        self.assertEqual(select_stmt.orderby_list[1][0].name, "REDNESS")
        self.assertEqual(select_stmt.orderby_list[1][1], ParserOrderBySortType.DESC)

    def test_select_statement_limit_class(self):
        """Testing limit clause in select statement
        Class: SelectStatement"""

        parser = Parser()

        select_query = "SELECT CLASS, REDNESS FROM TAIPAI \
                    WHERE (CLASS = 'VAN' AND REDNESS < 400 ) OR REDNESS > 700 \
                    ORDER BY CLASS, REDNESS DESC LIMIT 3;"

        evadb_statement_list = parser.parse(select_query)
        self.assertIsInstance(evadb_statement_list, list)
        self.assertEqual(len(evadb_statement_list), 1)
        self.assertEqual(evadb_statement_list[0].stmt_type, StatementType.SELECT)

        select_stmt = evadb_statement_list[0]

        # target List
        self.assertIsNotNone(select_stmt.target_list)
        self.assertEqual(len(select_stmt.target_list), 2)
        self.assertEqual(select_stmt.target_list[0].etype, ExpressionType.TUPLE_VALUE)
        self.assertEqual(select_stmt.target_list[1].etype, ExpressionType.TUPLE_VALUE)

        # from_table
        self.assertIsNotNone(select_stmt.from_table)
        self.assertIsInstance(select_stmt.from_table, TableRef)
        self.assertEqual(select_stmt.from_table.table.table_name, "TAIPAI")

        # where_clause
        self.assertIsNotNone(select_stmt.where_clause)

        # orderby_clause
        self.assertIsNotNone(select_stmt.orderby_list)
        self.assertEqual(len(select_stmt.orderby_list), 2)
        self.assertEqual(select_stmt.orderby_list[0][0].name, "CLASS")
        self.assertEqual(select_stmt.orderby_list[0][1], ParserOrderBySortType.ASC)
        self.assertEqual(select_stmt.orderby_list[1][0].name, "REDNESS")
        self.assertEqual(select_stmt.orderby_list[1][1], ParserOrderBySortType.DESC)

        # limit_count
        self.assertIsNotNone(select_stmt.limit_count)
        self.assertEqual(select_stmt.limit_count, ConstantValueExpression(3))

    def test_select_statement_sample_class(self):
        """Testing sample frequency"""

        parser = Parser()

        select_query = "SELECT CLASS, REDNESS FROM TAIPAI SAMPLE 5;"

        evadb_statement_list = parser.parse(select_query)
        self.assertIsInstance(evadb_statement_list, list)
        self.assertEqual(len(evadb_statement_list), 1)
        self.assertEqual(evadb_statement_list[0].stmt_type, StatementType.SELECT)

        select_stmt = evadb_statement_list[0]

        # target List
        self.assertIsNotNone(select_stmt.target_list)
        self.assertEqual(len(select_stmt.target_list), 2)
        self.assertEqual(select_stmt.target_list[0].etype, ExpressionType.TUPLE_VALUE)
        self.assertEqual(select_stmt.target_list[1].etype, ExpressionType.TUPLE_VALUE)

        # from_table
        self.assertIsNotNone(select_stmt.from_table)
        self.assertIsInstance(select_stmt.from_table, TableRef)
        self.assertEqual(select_stmt.from_table.table.table_name, "TAIPAI")

        # sample_freq
        self.assertEqual(select_stmt.from_table.sample_freq, ConstantValueExpression(5))

    def test_select_function_star(self):
        parser = Parser()

        query = "SELECT DemoFunc(*) FROM DemoDB.DemoTable;"
        evadb_stmt_list = parser.parse(query)

        # check stmt itself
        self.assertIsInstance(evadb_stmt_list, list)
        self.assertEqual(len(evadb_stmt_list), 1)
        self.assertEqual(evadb_stmt_list[0].stmt_type, StatementType.SELECT)
        select_stmt = evadb_stmt_list[0]

        # target List
        self.assertIsNotNone(select_stmt.target_list)
        self.assertEqual(len(select_stmt.target_list), 1)
        self.assertEqual(
            select_stmt.target_list[0].etype, ExpressionType.FUNCTION_EXPRESSION
        )
        self.assertEqual(len(select_stmt.target_list[0].children), 1)
        self.assertEqual(
            select_stmt.target_list[0].children[0].etype, ExpressionType.TUPLE_VALUE
        )
        self.assertEqual(select_stmt.target_list[0].children[0].name, "*")

        # from_table
        self.assertIsNotNone(select_stmt.from_table)
        self.assertIsInstance(select_stmt.from_table, TableRef)
        self.assertEqual(select_stmt.from_table.table.table_name, "DemoTable")
        self.assertEqual(select_stmt.from_table.table.database_name, "DemoDB")

    def test_select_without_table_source(self):
        parser = Parser()

        query = "SELECT DemoFunc(12);"
        evadb_stmt_list = parser.parse(query)

        # check stmt itself
        self.assertIsInstance(evadb_stmt_list, list)
        self.assertEqual(len(evadb_stmt_list), 1)
        self.assertEqual(evadb_stmt_list[0].stmt_type, StatementType.SELECT)
        select_stmt = evadb_stmt_list[0]

        # target List
        self.assertIsNotNone(select_stmt.target_list)
        self.assertEqual(len(select_stmt.target_list), 1)
        self.assertEqual(
            select_stmt.target_list[0].etype, ExpressionType.FUNCTION_EXPRESSION
        )
        self.assertEqual(len(select_stmt.target_list[0].children), 1)
        self.assertEqual(
            select_stmt.target_list[0].children[0].etype, ExpressionType.CONSTANT_VALUE
        )
        self.assertEqual(select_stmt.target_list[0].children[0].value, 12)

        # from_table
        self.assertIsNone(select_stmt.from_table)

    def test_table_ref(self):
        """Testing table info in TableRef
        Class: TableInfo
        """
        table_info = TableInfo("TAIPAI", "Schema", "Database")
        table_ref_obj = TableRef(table_info)
        select_stmt_new = SelectStatement()
        select_stmt_new.from_table = table_ref_obj
        self.assertEqual(select_stmt_new.from_table.table.table_name, "TAIPAI")
        self.assertEqual(select_stmt_new.from_table.table.schema_name, "Schema")
        self.assertEqual(select_stmt_new.from_table.table.database_name, "Database")

    def test_insert_statement(self):
        parser = Parser()
        insert_query = """INSERT INTO MyVideo (Frame_ID, Frame_Path)
                                    VALUES    (1, '/mnt/frames/1.png');
                        """
        expected_stmt = InsertTableStatement(
            TableRef(TableInfo("MyVideo")),
            [
                TupleValueExpression("Frame_ID"),
                TupleValueExpression("Frame_Path"),
            ],
            [
                ConstantValueExpression(1),
                ConstantValueExpression("/mnt/frames/1.png", ColumnType.TEXT),
            ],
        )
        evadb_statement_list = parser.parse(insert_query)
        self.assertIsInstance(evadb_statement_list, list)
        self.assertEqual(len(evadb_statement_list), 1)
        self.assertEqual(evadb_statement_list[0].stmt_type, StatementType.INSERT)

        insert_stmt = evadb_statement_list[0]
        self.assertEqual(insert_stmt, expected_stmt)

    def test_delete_statement(self):
        parser = Parser()
        delete_statement = """DELETE FROM Foo WHERE id > 5"""

        evadb_statement_list = parser.parse(delete_statement)
        self.assertIsInstance(evadb_statement_list, list)
        self.assertEqual(len(evadb_statement_list), 1)
        self.assertEqual(evadb_statement_list[0].stmt_type, StatementType.DELETE)

        delete_stmt = evadb_statement_list[0]

        expected_stmt = DeleteTableStatement(
            TableRef(TableInfo("Foo")),
            ComparisonExpression(
                ExpressionType.COMPARE_GREATER,
                TupleValueExpression("id"),
                ConstantValueExpression(5),
            ),
        )

        self.assertEqual(delete_stmt, expected_stmt)

    def test_set_statement(self):
        parser = Parser()
        set_statement = """SET OPENAIKEY = 'ABCD'"""
        evadb_statement_list = parser.parse(set_statement)

        self.assertIsInstance(evadb_statement_list, list)
        self.assertEqual(len(evadb_statement_list), 1)
        self.assertEqual(evadb_statement_list[0].stmt_type, StatementType.SET)

        set_stmt = evadb_statement_list[0]

        expected_stmt = SetStatement(
            "OPENAIKEY", ConstantValueExpression("ABCD", ColumnType.TEXT)
        )

        self.assertEqual(set_stmt, expected_stmt)

        # TESTING 'TO' IN PLACE OF '='
        set_statement = """SET OPENAIKEY TO 'ABCD'"""
        evadb_statement_list = parser.parse(set_statement)

        self.assertIsInstance(evadb_statement_list, list)
        self.assertEqual(len(evadb_statement_list), 1)
        self.assertEqual(evadb_statement_list[0].stmt_type, StatementType.SET)

        set_stmt = evadb_statement_list[0]

        expected_stmt = SetStatement(
            "OPENAIKEY", ConstantValueExpression("ABCD", ColumnType.TEXT)
        )

        self.assertEqual(set_stmt, expected_stmt)

    def test_show_config_statement(self):
        parser = Parser()
        show_config_statement = """SHOW OPENAIKEY"""
        evadb_statement_list = parser.parse(show_config_statement)

        self.assertIsInstance(evadb_statement_list, list)
        self.assertEqual(len(evadb_statement_list), 1)
        self.assertEqual(evadb_statement_list[0].stmt_type, StatementType.SHOW)

        show_config_stmt = evadb_statement_list[0]

        expected_stmt = ShowStatement(show_type=ShowType.CONFIGS, show_val="OPENAIKEY")

        self.assertEqual(show_config_stmt, expected_stmt)

    def test_create_predict_function_statement(self):
        parser = Parser()
        create_func_query = """
            CREATE OR REPLACE FUNCTION HomeSalesForecast FROM
            ( SELECT * FROM postgres_data.home_sales )
            TYPE Forecasting
            PREDICT 'price';
        """
        evadb_statement_list = parser.parse(create_func_query)
        self.assertIsInstance(evadb_statement_list, list)
        self.assertEqual(len(evadb_statement_list), 1)
        self.assertEqual(
            evadb_statement_list[0].stmt_type, StatementType.CREATE_FUNCTION
        )
        create_func_stmt = evadb_statement_list[0]
        self.assertEqual(create_func_stmt.name, "HomeSalesForecast")
        self.assertEqual(create_func_stmt.or_replace, True)
        self.assertEqual(create_func_stmt.if_not_exists, False)
        self.assertEqual(create_func_stmt.impl_path, None)
        self.assertEqual(create_func_stmt.inputs, [])
        self.assertEqual(create_func_stmt.outputs, [])
        self.assertEqual(create_func_stmt.function_type, "Forecasting")
        self.assertEqual(create_func_stmt.metadata, [("predict", "price")])

        nested_select_stmt = create_func_stmt.query
        self.assertEqual(nested_select_stmt.stmt_type, StatementType.SELECT)
        self.assertEqual(len(nested_select_stmt.target_list), 1)
        self.assertEqual(
            nested_select_stmt.target_list[0].etype, ExpressionType.TUPLE_VALUE
        )
        self.assertEqual(nested_select_stmt.target_list[0].name, "*")
        self.assertIsInstance(nested_select_stmt.from_table, TableRef)
        self.assertIsInstance(nested_select_stmt.from_table.table, TableInfo)
        self.assertEqual(nested_select_stmt.from_table.table.table_name, "home_sales")
        self.assertEqual(
            nested_select_stmt.from_table.table.database_name, "postgres_data"
        )

    def test_create_function_statement(self):
        parser = Parser()
        create_func_query = """CREATE FUNCTION IF NOT EXISTS FastRCNN
                  INPUT  (Frame_Array NDARRAY UINT8(3, 256, 256))
                  OUTPUT (Labels NDARRAY STR(10), Bbox NDARRAY UINT8(10, 4))
                  TYPE  Classification
                  IMPL  'data/fastrcnn.py'
                  PREDICT "VALUE";
        """

        expected_cci = ColConstraintInfo()
        expected_cci.nullable = True
        expected_stmt = CreateFunctionStatement(
            "FastRCNN",
            False,
            True,
            Path("data/fastrcnn.py"),
            [
                ColumnDefinition(
                    "Frame_Array",
                    ColumnType.NDARRAY,
                    NdArrayType.UINT8,
                    (3, 256, 256),
                    expected_cci,
                )
            ],
            [
                ColumnDefinition(
                    "Labels", ColumnType.NDARRAY, NdArrayType.STR, (10,), expected_cci
                ),
                ColumnDefinition(
                    "Bbox", ColumnType.NDARRAY, NdArrayType.UINT8, (10, 4), expected_cci
                ),
            ],
            "Classification",
            None,
            [("predict", "VALUE")],
        )
        evadb_statement_list = parser.parse(create_func_query)
        self.assertIsInstance(evadb_statement_list, list)
        self.assertEqual(len(evadb_statement_list), 1)
        self.assertEqual(
            evadb_statement_list[0].stmt_type, StatementType.CREATE_FUNCTION
        )
        self.assertEqual(str(evadb_statement_list[0]), str(expected_stmt))

        create_func_stmt = evadb_statement_list[0]

        self.assertEqual(create_func_stmt, expected_stmt)

    def test_load_video_data_statement(self):
        parser = Parser()
        load_data_query = """LOAD VIDEO 'data/video.mp4'
                             INTO MyVideo"""
        file_options = {}
        file_options["file_format"] = FileFormatType.VIDEO
        column_list = None
        expected_stmt = LoadDataStatement(
            TableInfo("MyVideo"),
            Path("data/video.mp4"),
            column_list,
            file_options,
        )
        evadb_statement_list = parser.parse(load_data_query)
        self.assertIsInstance(evadb_statement_list, list)
        self.assertEqual(len(evadb_statement_list), 1)
        self.assertEqual(evadb_statement_list[0].stmt_type, StatementType.LOAD_DATA)

        load_data_stmt = evadb_statement_list[0]
        self.assertEqual(load_data_stmt, expected_stmt)

    def test_load_csv_data_statement(self):
        parser = Parser()
        load_data_query = """LOAD CSV 'data/meta.csv'
                             INTO
                             MyMeta (id, frame_id, video_id, label);"""
        file_options = {}
        file_options["file_format"] = FileFormatType.CSV
        expected_stmt = LoadDataStatement(
            TableInfo("MyMeta"),
            Path("data/meta.csv"),
            [
                TupleValueExpression("id"),
                TupleValueExpression("frame_id"),
                TupleValueExpression("video_id"),
                TupleValueExpression("label"),
            ],
            file_options,
        )
        evadb_statement_list = parser.parse(load_data_query)
        self.assertIsInstance(evadb_statement_list, list)
        self.assertEqual(len(evadb_statement_list), 1)
        self.assertEqual(evadb_statement_list[0].stmt_type, StatementType.LOAD_DATA)

        load_data_stmt = evadb_statement_list[0]
        self.assertEqual(load_data_stmt, expected_stmt)

    def test_nested_select_statement(self):
        parser = Parser()
        sub_query = """SELECT CLASS FROM TAIPAI WHERE CLASS = 'VAN'"""
        nested_query = """SELECT ID FROM ({}) AS T;""".format(sub_query)
        parsed_sub_query = parser.parse(sub_query)[0]
        actual_stmt = parser.parse(nested_query)[0]
        self.assertEqual(actual_stmt.stmt_type, StatementType.SELECT)
        self.assertEqual(actual_stmt.target_list[0].name, "ID")
        self.assertEqual(
            actual_stmt.from_table, TableRef(parsed_sub_query, alias=Alias("T"))
        )

        sub_query = """SELECT Yolo(frame).bbox FROM autonomous_vehicle_1
                              WHERE Yolo(frame).label = 'vehicle'"""
        nested_query = """SELECT Licence_plate(bbox) FROM
                            ({}) AS T
                          WHERE Is_suspicious(bbox) = 1 AND
                                Licence_plate(bbox) = '12345';
                      """.format(
            sub_query
        )
        query = """SELECT Licence_plate(bbox) FROM TAIPAI
                    WHERE Is_suspicious(bbox) = 1 AND
                        Licence_plate(bbox) = '12345';
                """
        query_stmt = parser.parse(query)[0]
        actual_stmt = parser.parse(nested_query)[0]
        sub_query_stmt = parser.parse(sub_query)[0]
        self.assertEqual(
            actual_stmt.from_table, TableRef(sub_query_stmt, alias=Alias("T"))
        )
        self.assertEqual(actual_stmt.where_clause, query_stmt.where_clause)
        self.assertEqual(actual_stmt.target_list, query_stmt.target_list)

    def test_should_return_false_for_unequal_expression(self):
        table = TableRef(TableInfo("MyVideo"))
        load_stmt = LoadDataStatement(
            table, Path("data/video.mp4"), FileFormatType.VIDEO
        )
        insert_stmt = InsertTableStatement(table)
        create_func = CreateFunctionStatement(
            "func",
            False,
            False,
            Path("data/fastrcnn.py"),
            [
                ColumnDefinition(
                    "frame",
                    ColumnType.NDARRAY,
                    NdArrayType.UINT8,
                    (3, 256, 256),
                )
            ],
            [ColumnDefinition("labels", ColumnType.NDARRAY, NdArrayType.STR, (10))],
            "Classification",
        )
        select_stmt = SelectStatement()
        self.assertNotEqual(load_stmt, insert_stmt)
        self.assertNotEqual(insert_stmt, load_stmt)
        self.assertNotEqual(create_func, insert_stmt)
        self.assertNotEqual(select_stmt, create_func)

    def test_create_table_from_select(self):
        select_query = """SELECT id, Yolo(frame).labels FROM MyVideo
                        WHERE id<5; """
        query = "CREATE TABLE uadtrac_fastRCNN AS {}".format(select_query)
        parser = Parser()
        mat_view_stmt = parser.parse(query)
        select_stmt = parser.parse(select_query)
        expected_stmt = CreateTableStatement(
            TableInfo("uadtrac_fastRCNN"),
            False,
            [],
            select_stmt[0],
        )
        self.assertEqual(mat_view_stmt[0], expected_stmt)

    def test_join(self):
        select_query = """SELECT table1.a FROM table1 JOIN table2
                    ON table1.a = table2.a; """
        parser = Parser()
        select_stmt = parser.parse(select_query)[0]
        table1_col_a = TupleValueExpression("a", "table1")
        table2_col_a = TupleValueExpression("a", "table2")
        select_list = [table1_col_a]
        from_table = TableRef(
            JoinNode(
                TableRef(TableInfo("table1")),
                TableRef(TableInfo("table2")),
                predicate=ComparisonExpression(
                    ExpressionType.COMPARE_EQUAL, table1_col_a, table2_col_a
                ),
                join_type=JoinType.INNER_JOIN,
            )
        )
        expected_stmt = SelectStatement(select_list, from_table)

        self.assertEqual(select_stmt, expected_stmt)

    def test_join_with_where(self):
        select_query = """SELECT table1.a FROM table1 JOIN table2
            ON table1.a = table2.a WHERE table1.a <= 5"""
        parser = Parser()
        select_stmt = parser.parse(select_query)[0]
        table1_col_a = TupleValueExpression("a", "table1")
        table2_col_a = TupleValueExpression("a", "table2")
        select_list = [table1_col_a]
        from_table = TableRef(
            JoinNode(
                TableRef(TableInfo("table1")),
                TableRef(TableInfo("table2")),
                predicate=ComparisonExpression(
                    ExpressionType.COMPARE_EQUAL, table1_col_a, table2_col_a
                ),
                join_type=JoinType.INNER_JOIN,
            )
        )
        where_clause = ComparisonExpression(
            ExpressionType.COMPARE_LEQ,
            table1_col_a,
            ConstantValueExpression(5),
        )
        expected_stmt = SelectStatement(select_list, from_table, where_clause)
        self.assertEqual(select_stmt, expected_stmt)

    def test_multiple_join_with_multiple_ON(self):
        select_query = """SELECT table1.a FROM table1 JOIN table2
            ON table1.a = table2.a JOIN table3
            ON table3.a = table1.a WHERE table1.a <= 5"""
        parser = Parser()
        select_stmt = parser.parse(select_query)[0]
        table1_col_a = TupleValueExpression("a", "table1")
        table2_col_a = TupleValueExpression("a", "table2")
        table3_col_a = TupleValueExpression("a", "table3")
        select_list = [table1_col_a]
        child_join = TableRef(
            JoinNode(
                TableRef(TableInfo("table1")),
                TableRef(TableInfo("table2")),
                predicate=ComparisonExpression(
                    ExpressionType.COMPARE_EQUAL, table1_col_a, table2_col_a
                ),
                join_type=JoinType.INNER_JOIN,
            )
        )

        from_table = TableRef(
            JoinNode(
                child_join,
                TableRef(TableInfo("table3")),
                predicate=ComparisonExpression(
                    ExpressionType.COMPARE_EQUAL, table3_col_a, table1_col_a
                ),
                join_type=JoinType.INNER_JOIN,
            )
        )
        where_clause = ComparisonExpression(
            ExpressionType.COMPARE_LEQ,
            table1_col_a,
            ConstantValueExpression(5),
        )
        expected_stmt = SelectStatement(select_list, from_table, where_clause)
        self.assertEqual(select_stmt, expected_stmt)

    def test_lateral_join(self):
        select_query = """SELECT frame FROM MyVideo JOIN LATERAL
                            ObjectDet(frame) AS OD;"""
        parser = Parser()
        select_stmt = parser.parse(select_query)[0]
        tuple_frame = TupleValueExpression("frame")
        func_expr = FunctionExpression(
            func=None, name="ObjectDet", children=[tuple_frame]
        )
        from_table = TableRef(
            JoinNode(
                TableRef(TableInfo("MyVideo")),
                TableRef(TableValuedExpression(func_expr), alias=Alias("OD")),
                join_type=JoinType.LATERAL_JOIN,
            )
        )
        expected_stmt = SelectStatement([tuple_frame], from_table)
        self.assertEqual(select_stmt, expected_stmt)

    def test_class_equality(self):
        table_info = TableInfo("MyVideo")
        table_ref = TableRef(TableInfo("MyVideo"))
        tuple_frame = TupleValueExpression("frame")
        func_expr = FunctionExpression(
            func=None, name="ObjectDet", children=[tuple_frame]
        )
        join_node = JoinNode(
            TableRef(TableInfo("MyVideo")),
            TableRef(TableValuedExpression(func_expr), alias=Alias("OD")),
            join_type=JoinType.LATERAL_JOIN,
        )
        self.assertNotEqual(table_info, table_ref)
        self.assertNotEqual(tuple_frame, table_ref)
        self.assertNotEqual(join_node, table_ref)
        self.assertNotEqual(table_ref, table_info)

    def test_create_job(self):
        queries = [
            """CREATE OR REPLACE FUNCTION HomeSalesForecast FROM
                ( SELECT * FROM postgres_data.home_sales )
                TYPE Forecasting
                PREDICT 'price';""",
            "Select HomeSalesForecast(10);",
        ]
        job_query = f"""CREATE JOB my_job AS {{
            {''.join(queries)}
        }}
        START '2023-04-01'
        END '2023-05-01'
        EVERY 2 hour
        """

        parser = Parser()
        job_stmt = parser.parse(job_query)[0]
        self.assertEqual(job_stmt.job_name, "my_job")
        self.assertEqual(len(job_stmt.queries), 2)
        self.assertTrue(queries[0].rstrip(";") == str(job_stmt.queries[0]))
        self.assertTrue(queries[1].rstrip(";") == str(job_stmt.queries[1]))
        self.assertEqual(job_stmt.start_time, "2023-04-01")
        self.assertEqual(job_stmt.end_time, "2023-05-01")
        self.assertEqual(job_stmt.repeat_interval, 2)
        self.assertEqual(job_stmt.repeat_period, "hour")
