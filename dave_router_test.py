#!/usr/bin/env python3
"""
Unit tests for dave_router.py tunnel mode alignment.

This test suite verifies that the client-side connection logic correctly
replicates the backend adapter behavior for multi-schema and multi-dialect support.
"""

import unittest
from unittest.mock import patch, MagicMock, AsyncMock
import json
import base64
import msgpack
import sqlalchemy
from dave_router import handle_sql_query


class TestDaveRouterTunnelMode(unittest.TestCase):
    """Test cases for tunnel mode alignment in dave_router.py."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_logger = MagicMock()
        self.mock_websocket = MagicMock()

    @patch('dave_router.sqlalchemy.create_engine')
    @patch('dave_router.message_queue')
    def test_postgresql_multi_schema_connection(self, mock_queue, mock_create_engine):
        """Test PostgreSQL multi-schema connection logic."""
        # Mock data with multi-schema parameters
        data = {
            "connectionObject": {
                "dialect": "postgresql",
                "user": "test_user",
                "password": "test_pass",
                "host": "localhost",
                "port": "5432",
                "database": "test_db",
                "schemas": ["sales", "marketing"]  # Multi-schema parameter
            },
            "query": "SELECT 1",
            "request_id": "test_id"
        }

        # Mock engine and connection
        mock_engine = MagicMock()
        mock_connection = MagicMock()
        mock_result = MagicMock()
        
        mock_engine.connect.return_value.__enter__.return_value = mock_connection
        mock_connection.execute.return_value = mock_result
        mock_result.returns_rows = True
        mock_result.fetchall.return_value = [[1]]
        mock_result.keys.return_value = ["col1"]
        mock_result.rowcount = 1
        
        mock_create_engine.return_value = mock_engine

        # Call the function
        handle_sql_query(data, self.mock_logger)

        # Verify the correct URL and connect_args were used
        mock_create_engine.assert_called_once()
        call_args = mock_create_engine.call_args
        
        # Check URL
        self.assertIn("postgresql+psycopg2://test_user:test_pass@localhost:5432/test_db", call_args[0][0])
        
        # Check connect_args for multi-schema
        connect_args = call_args[1]['connect_args']
        self.assertIn('options', connect_args)
        self.assertIn('search_path="sales","marketing"', connect_args['options'])

    @patch('dave_router.sqlalchemy.create_engine')
    @patch('dave_router.message_queue')
    def test_postgresql_single_schema_connection(self, mock_queue, mock_create_engine):
        """Test PostgreSQL single-schema connection logic."""
        # Mock data with single schema parameter
        data = {
            "connectionObject": {
                "dialect": "postgresql",
                "user": "test_user",
                "password": "test_pass",
                "host": "localhost",
                "port": "5432",
                "database": "test_db",
                "schema": "public"  # Single schema parameter
            },
            "query": "SELECT 1",
            "request_id": "test_id"
        }

        # Mock engine and connection
        mock_engine = MagicMock()
        mock_connection = MagicMock()
        mock_result = MagicMock()
        
        mock_engine.connect.return_value.__enter__.return_value = mock_connection
        mock_connection.execute.return_value = mock_result
        mock_result.returns_rows = True
        mock_result.fetchall.return_value = [[1]]
        mock_result.keys.return_value = ["col1"]
        mock_result.rowcount = 1
        
        mock_create_engine.return_value = mock_engine

        # Call the function
        handle_sql_query(data, self.mock_logger)

        # Verify the correct URL and connect_args were used
        mock_create_engine.assert_called_once()
        call_args = mock_create_engine.call_args
        
        # Check URL
        self.assertIn("postgresql+psycopg2://test_user:test_pass@localhost:5432/test_db", call_args[0][0])
        
        # Check connect_args for single schema
        connect_args = call_args[1]['connect_args']
        self.assertIn('options', connect_args)
        self.assertIn('search_path=public', connect_args['options'])

    @patch('dave_router.sqlalchemy.create_engine')
    @patch('dave_router.message_queue')
    def test_snowflake_connection_with_params(self, mock_queue, mock_create_engine):
        """Test Snowflake connection with warehouse and role parameters."""
        # Mock data with Snowflake parameters
        data = {
            "connectionObject": {
                "dialect": "snowflake",
                "user": "test_user",
                "password": "test_pass",
                "host": "test_account.snowflakecomputing.com",
                "port": "443",
                "database": "test_db",
                "schema": "test_schema",
                "warehouse": "COMPUTE_WH",
                "role": "ANALYST"
            },
            "query": "SELECT 1",
            "request_id": "test_id"
        }

        # Mock engine and connection
        mock_engine = MagicMock()
        mock_connection = MagicMock()
        mock_result = MagicMock()
        
        mock_engine.connect.return_value.__enter__.return_value = mock_connection
        mock_connection.execute.return_value = mock_result
        mock_result.returns_rows = True
        mock_result.fetchall.return_value = [[1]]
        mock_result.keys.return_value = ["col1"]
        mock_result.rowcount = 1
        
        mock_create_engine.return_value = mock_engine

        # Call the function
        handle_sql_query(data, self.mock_logger)

        # Verify the correct URL was used
        mock_create_engine.assert_called_once()
        call_args = mock_create_engine.call_args
        
        # Check URL contains Snowflake parameters
        url = call_args[0][0]
        self.assertIn("snowflake://test_user:test_pass@test_account.snowflakecomputing.com:443/test_db", url)
        self.assertIn("schema=test_schema", url)
        self.assertIn("warehouse=COMPUTE_WH", url)
        self.assertIn("role=ANALYST", url)

    @patch('dave_router.sqlalchemy.create_engine')
    @patch('dave_router.message_queue')
    def test_bigquery_connection_with_dataset(self, mock_queue, mock_create_engine):
        """Test BigQuery connection with dataset parameter."""
        # Mock data with BigQuery parameters
        data = {
            "connectionObject": {
                "dialect": "bigquery",
                "user": "test_user",
                "password": "test_pass",
                "host": "test-project-id",
                "port": "443",
                "database": "test-project-id",  # Maps to project_id
                "schema": "test_dataset"  # Maps to dataset
            },
            "query": "SELECT 1",
            "request_id": "test_id"
        }

        # Mock engine and connection
        mock_engine = MagicMock()
        mock_connection = MagicMock()
        mock_result = MagicMock()
        
        mock_engine.connect.return_value.__enter__.return_value = mock_connection
        mock_connection.execute.return_value = mock_result
        mock_result.returns_rows = True
        mock_result.fetchall.return_value = [[1]]
        mock_result.keys.return_value = ["col1"]
        mock_result.rowcount = 1
        
        mock_create_engine.return_value = mock_engine

        # Call the function
        handle_sql_query(data, self.mock_logger)

        # Verify the correct URL was used
        mock_create_engine.assert_called_once()
        call_args = mock_create_engine.call_args
        
        # Check URL for BigQuery with dataset
        url = call_args[0][0]
        self.assertEqual(url, "bigquery://test-project-id/test_dataset")

    @patch('dave_router.sqlalchemy.create_engine')
    @patch('dave_router.message_queue')
    def test_bigquery_connection_without_dataset(self, mock_queue, mock_create_engine):
        """Test BigQuery connection without dataset parameter."""
        # Mock data with BigQuery parameters (no dataset)
        data = {
            "connectionObject": {
                "dialect": "bigquery",
                "user": "test_user",
                "password": "test_pass",
                "host": "test-project-id",
                "port": "443",
                "database": "test-project-id"  # Maps to project_id
                # No schema/dataset parameter
            },
            "query": "SELECT 1",
            "request_id": "test_id"
        }

        # Mock engine and connection
        mock_engine = MagicMock()
        mock_connection = MagicMock()
        mock_result = MagicMock()
        
        mock_engine.connect.return_value.__enter__.return_value = mock_connection
        mock_connection.execute.return_value = mock_result
        mock_result.returns_rows = True
        mock_result.fetchall.return_value = [[1]]
        mock_result.keys.return_value = ["col1"]
        mock_result.rowcount = 1
        
        mock_create_engine.return_value = mock_engine

        # Call the function
        handle_sql_query(data, self.mock_logger)

        # Verify the correct URL was used
        mock_create_engine.assert_called_once()
        call_args = mock_create_engine.call_args
        
        # Check URL for BigQuery without dataset
        url = call_args[0][0]
        self.assertEqual(url, "bigquery://test-project-id")

    @patch('dave_router.sqlalchemy.create_engine')
    @patch('dave_router.message_queue')
    def test_mysql_connection(self, mock_queue, mock_create_engine):
        """Test MySQL connection logic."""
        # Mock data with MySQL parameters
        data = {
            "connectionObject": {
                "dialect": "mysql",
                "user": "test_user",
                "password": "test_pass",
                "host": "localhost",
                "port": "3306",
                "database": "test_db"
            },
            "query": "SELECT 1",
            "request_id": "test_id"
        }

        # Mock engine and connection
        mock_engine = MagicMock()
        mock_connection = MagicMock()
        mock_result = MagicMock()
        
        mock_engine.connect.return_value.__enter__.return_value = mock_connection
        mock_connection.execute.return_value = mock_result
        mock_result.returns_rows = True
        mock_result.fetchall.return_value = [[1]]
        mock_result.keys.return_value = ["col1"]
        mock_result.rowcount = 1
        
        mock_create_engine.return_value = mock_engine

        # Call the function
        handle_sql_query(data, self.mock_logger)

        # Verify the correct URL was used
        mock_create_engine.assert_called_once()
        call_args = mock_create_engine.call_args
        
        # Check URL for MySQL
        url = call_args[0][0]
        self.assertEqual(url, "mysql+pymysql://test_user:test_pass@localhost:3306/test_db")

    @patch('dave_router.sqlalchemy.create_engine')
    @patch('dave_router.message_queue')
    def test_connection_error_handling(self, mock_queue, mock_create_engine):
        """Test error handling when connection fails."""
        # Mock data
        data = {
            "connectionObject": {
                "dialect": "postgresql",
                "user": "test_user",
                "password": "test_pass",
                "host": "localhost",
                "port": "5432",
                "database": "test_db"
            },
            "query": "SELECT 1",
            "request_id": "test_id"
        }

        # Mock engine to raise an exception
        mock_create_engine.side_effect = Exception("Connection failed")

        # Call the function
        handle_sql_query(data, self.mock_logger)

        # Verify error was logged
        self.mock_logger.error.assert_called()
        error_call = self.mock_logger.error.call_args[0][0]
        self.assertIn("Query error: request_id=test_id", error_call)

    def test_missing_connection_parameters(self):
        """Test handling of missing connection parameters."""
        # Mock data with missing required parameters
        data = {
            "connectionObject": {
                "dialect": "postgresql"
                # Missing user, password, host, port, database
            },
            "query": "SELECT 1",
            "request_id": "test_id"
        }

        # Call the function - should handle gracefully
        handle_sql_query(data, self.mock_logger)

        # Verify error was logged
        self.mock_logger.error.assert_called()


if __name__ == '__main__':
    unittest.main() 