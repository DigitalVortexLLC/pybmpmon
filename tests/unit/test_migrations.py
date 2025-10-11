"""Unit tests for migration system."""

from pathlib import Path
from unittest import mock

import pytest
from pybmpmon.database.migrations import Migration, MigrationRunner


class TestMigration:
    """Test Migration class."""

    def test_migration_checksum(self, tmp_path: Path) -> None:
        """Test migration checksum calculation."""
        # Create test migration file
        migration_file = tmp_path / "001_test.sql"
        migration_file.write_text("SELECT 1;")

        migration = Migration(version=1, name="test", file_path=migration_file)

        # Verify checksum is consistent
        checksum1 = migration.checksum
        checksum2 = migration.checksum
        assert checksum1 == checksum2

        # Verify checksum changes when content changes
        migration_file.write_text("SELECT 2;")
        checksum3 = migration.checksum
        assert checksum1 != checksum3

    def test_migration_sql_property(self, tmp_path: Path) -> None:
        """Test migration SQL content reading."""
        migration_file = tmp_path / "001_test.sql"
        sql_content = "CREATE TABLE test (id INTEGER);"
        migration_file.write_text(sql_content)

        migration = Migration(version=1, name="test", file_path=migration_file)

        assert migration.sql == sql_content


class TestMigrationRunner:
    """Test MigrationRunner class."""

    def test_load_migrations(self, tmp_path: Path) -> None:
        """Test loading migrations from directory."""
        # Create test migrations
        (tmp_path / "001_first.sql").write_text("SELECT 1;")
        (tmp_path / "002_second.sql").write_text("SELECT 2;")
        (tmp_path / "003_third.sql").write_text("SELECT 3;")

        # Mock runner with test directory
        runner = MigrationRunner(mock.MagicMock())
        runner.migrations_dir = tmp_path

        migrations = runner._load_migrations()

        assert len(migrations) == 3
        assert migrations[0].version == 1
        assert migrations[0].name == "first"
        assert migrations[1].version == 2
        assert migrations[1].name == "second"
        assert migrations[2].version == 3
        assert migrations[2].name == "third"

    def test_load_migrations_invalid_filename(self, tmp_path: Path) -> None:
        """Test loading migrations with invalid filenames."""
        # Create migrations with invalid names
        (tmp_path / "001_valid.sql").write_text("SELECT 1;")
        (tmp_path / "invalid.sql").write_text("SELECT 2;")
        (tmp_path / "abc_invalid.sql").write_text("SELECT 3;")

        runner = MigrationRunner(mock.MagicMock())
        runner.migrations_dir = tmp_path

        migrations = runner._load_migrations()

        # Only valid migration should be loaded
        assert len(migrations) == 1
        assert migrations[0].version == 1
        assert migrations[0].name == "valid"

    @pytest.mark.asyncio
    async def test_get_pending_migrations_fresh_database(self, tmp_path: Path) -> None:
        """Test getting pending migrations on fresh database."""
        # Create test migrations
        (tmp_path / "001_first.sql").write_text("SELECT 1;")
        (tmp_path / "002_second.sql").write_text("SELECT 2;")

        # Mock pool that returns no schema_migrations table
        mock_conn = mock.MagicMock()
        mock_conn.fetchval = mock.AsyncMock(return_value=False)

        mock_pool = mock.MagicMock()
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

        runner = MigrationRunner(mock_pool)
        runner.migrations_dir = tmp_path

        pending = await runner.get_pending_migrations()

        # All migrations should be pending
        assert len(pending) == 2
        assert pending[0].version == 1
        assert pending[1].version == 2

    @pytest.mark.asyncio
    async def test_get_pending_migrations_checksum_mismatch(
        self, tmp_path: Path
    ) -> None:
        """Test checksum validation detects tampering."""
        # Create test migration
        migration_file = tmp_path / "001_test.sql"
        migration_file.write_text("SELECT 1;")

        migration = Migration(version=1, name="test", file_path=migration_file)
        original_checksum = migration.checksum  # noqa: F841

        # Mock pool that returns different checksum
        mock_conn = mock.MagicMock()
        mock_conn.fetchval = mock.AsyncMock(return_value=True)
        mock_conn.fetch = mock.AsyncMock(
            return_value=[{"version": 1, "checksum": "wrong_checksum"}]
        )

        mock_pool = mock.MagicMock()
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

        runner = MigrationRunner(mock_pool)
        runner.migrations_dir = tmp_path

        # Should raise error on checksum mismatch
        with pytest.raises(ValueError, match="checksum mismatch"):
            await runner.get_pending_migrations()

    @pytest.mark.asyncio
    async def test_get_pending_migrations_partial_applied(self, tmp_path: Path) -> None:
        """Test getting pending migrations when some are applied."""
        # Create test migrations
        (tmp_path / "001_first.sql").write_text("SELECT 1;")
        (tmp_path / "002_second.sql").write_text("SELECT 2;")
        (tmp_path / "003_third.sql").write_text("SELECT 3;")

        # Calculate checksums for first two migrations
        migration1 = Migration(
            version=1, name="first", file_path=tmp_path / "001_first.sql"
        )
        migration2 = Migration(
            version=2, name="second", file_path=tmp_path / "002_second.sql"
        )

        # Mock pool that returns first two migrations as applied
        mock_conn = mock.MagicMock()
        mock_conn.fetchval = mock.AsyncMock(return_value=True)
        mock_conn.fetch = mock.AsyncMock(
            return_value=[
                {"version": 1, "checksum": migration1.checksum},
                {"version": 2, "checksum": migration2.checksum},
            ]
        )

        mock_pool = mock.MagicMock()
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

        runner = MigrationRunner(mock_pool)
        runner.migrations_dir = tmp_path

        pending = await runner.get_pending_migrations()

        # Only third migration should be pending
        assert len(pending) == 1
        assert pending[0].version == 3
        assert pending[0].name == "third"
