"""Unit tests for security guardrails in mcp-ai-workforce.

Verifies path traversal protections and command execution restrictions:
1. validate_safe_path:
   - Valid paths inside workspace
   - Path traversal attempts with '../../'
   - Attempts to access C:\\Windows
   - Absolute paths outside the workspace
2. validate_safe_command:
   - Blocking destructive commands ('rm -rf', 'del /f', 'format c:', 'sudo')
   - Permitting safe developer commands ('pytest', 'git status')
"""

from pathlib import Path
import pytest

from src.guardrails import validate_safe_command, validate_safe_path


class TestValidateSafePath:
    """Suite testing path traversal defenses and workspace confinement."""

    def test_valid_paths_inside_workspace(self, tmp_path: Path):
        """Test that relative and absolute paths inside the workspace are allowed."""
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        child_dir = workspace / "src" / "worker"
        child_dir.mkdir(parents=True)
        child_file = child_dir / "app.py"
        child_file.write_text("print('safe')", encoding="utf-8")

        # Relative paths
        assert validate_safe_path("src/worker/app.py", workspace_root=workspace) == child_file.resolve()
        assert validate_safe_path(".", workspace_root=workspace) == workspace.resolve()
        assert validate_safe_path("src", workspace_root=workspace) == (workspace / "src").resolve()

        # Absolute path inside workspace
        assert validate_safe_path(child_file, workspace_root=workspace) == child_file.resolve()
        assert validate_safe_path(workspace, workspace_root=workspace) == workspace.resolve()

    def test_path_traversal_with_dot_dot_slash(self, tmp_path: Path):
        """Test that path traversal attempts using '../../' are blocked."""
        workspace = tmp_path / "workspace"
        workspace.mkdir()

        # Direct parent traversal
        with pytest.raises(PermissionError, match="outside authorized workspace root"):
            validate_safe_path("../../secret.txt", workspace_root=workspace)

        # Deep traversal
        with pytest.raises(PermissionError, match="outside authorized workspace root"):
            validate_safe_path("../../../etc/passwd", workspace_root=workspace)

        # Nested relative traversal escaping workspace
        with pytest.raises(PermissionError, match="outside authorized workspace root"):
            validate_safe_path("nested/dir/../../../../outside.txt", workspace_root=workspace)

    def test_access_windows_system_directory_blocked(self, tmp_path: Path):
        """Test that explicit attempts to access C:\\Windows or its descendants are blocked."""
        workspace = tmp_path / "workspace"
        workspace.mkdir()

        windows_paths = [
            r"C:\Windows",
            r"C:\Windows\System32",
            r"C:\Windows\System32\cmd.exe",
            "C:/Windows/notepad.exe",
            r"C:\Windows\System32\drivers\etc\hosts",
        ]

        for win_path in windows_paths:
            with pytest.raises(PermissionError, match="outside authorized workspace root|Access denied"):
                validate_safe_path(win_path, workspace_root=workspace)

        # POSIX system directories
        posix_paths = ["/etc/passwd", "/var/log", "/bin/sh", "/usr/bin"]
        for posix_path in posix_paths:
            with pytest.raises(PermissionError, match="outside authorized workspace root|Access denied"):
                validate_safe_path(posix_path, workspace_root=workspace)

    def test_absolute_paths_outside_workspace_blocked(self, tmp_path: Path):
        """Test that absolute paths pointing anywhere outside the workspace root are blocked."""
        workspace = tmp_path / "workspace"
        workspace.mkdir()

        outside_dir = tmp_path / "outside_dir"
        outside_dir.mkdir()
        outside_file = outside_dir / "config.json"
        outside_file.write_text("{}", encoding="utf-8")

        with pytest.raises(PermissionError, match="outside authorized workspace root"):
            validate_safe_path(outside_file, workspace_root=workspace)

        with pytest.raises(PermissionError, match="outside authorized workspace root"):
            validate_safe_path(str(outside_file.resolve()), workspace_root=workspace)

        with pytest.raises(PermissionError, match="outside authorized workspace root"):
            validate_safe_path(outside_dir, workspace_root=workspace)

    def test_sensitive_files_blocked(self, tmp_path: Path):
        """Test that access to .git, .env, server internals, and private keys is strictly forbidden."""
        workspace = tmp_path / "workspace"
        workspace.mkdir()

        # .env credentials protection
        with pytest.raises(PermissionError, match="sensitive path component.*forbidden"):
            validate_safe_path(".env", workspace_root=workspace)
        with pytest.raises(PermissionError, match="sensitive path component.*forbidden"):
            validate_safe_path(".env.local", workspace_root=workspace)

        # .git repository internals protection
        with pytest.raises(PermissionError, match="sensitive path component.*forbidden"):
            validate_safe_path(".git/config", workspace_root=workspace)

        # Agent server internal directory protection
        with pytest.raises(PermissionError, match="workforce server internal directory is forbidden"):
            validate_safe_path(".agents/mcp-ai-workforce/src/config.py", workspace_root=workspace)

        # Private keys protection
        with pytest.raises(PermissionError, match="sensitive key file.*forbidden"):
            validate_safe_path("secrets/server.pem", workspace_root=workspace)
        with pytest.raises(PermissionError, match="sensitive key file.*forbidden"):
            validate_safe_path("id_rsa", workspace_root=workspace)


class TestValidateSafeCommand:
    """Suite testing shell command inspection and destructive command blocking."""

    def test_blocking_rm_rf(self):
        """Test that 'rm -rf' command variations are strictly blocked."""
        rm_commands = [
            "rm -rf /",
            "rm -rf .",
            "rm -rf src/",
            "RM -RF node_modules",
            "rm -r -f data",
        ]
        for cmd in rm_commands:
            with pytest.raises(PermissionError, match="Destructive token .* detected"):
                validate_safe_command(cmd)

    def test_blocking_del_f(self):
        """Test that 'del /f' and Windows del variants are strictly blocked."""
        del_commands = [
            "del /f file.txt",
            "DEL /F /Q C:\\Windows",
            "del /f *.*",
            "del important.py",
            "DEL test.txt",
        ]
        for cmd in del_commands:
            with pytest.raises(PermissionError, match="Destructive token .* detected"):
                validate_safe_command(cmd)

    def test_blocking_format_c(self):
        """Test that 'format c:' and disk formatting commands are strictly blocked."""
        format_commands = [
            "format c:",
            "format C:",
            "FORMAT D: /FS:NTFS",
            "format volume",
            "format-volume -driveletter C",
        ]
        for cmd in format_commands:
            with pytest.raises(PermissionError, match="Destructive token .* detected"):
                validate_safe_command(cmd)

    def test_blocking_sudo(self):
        """Test that privilege escalation with 'sudo', 'su', or 'runas' is strictly blocked."""
        sudo_commands = [
            "sudo apt-get install",
            "SUDO rm test",
            "sudo systemctl restart nginx",
            "su - root",
            "runas /user:Administrator cmd",
        ]
        for cmd in sudo_commands:
            with pytest.raises(PermissionError, match="Destructive token .* detected"):
                validate_safe_command(cmd)

    def test_allowing_safe_commands_pytest_git_status(self):
        """Test that safe commands like 'pytest' and 'git status' are accepted without raising."""
        safe_commands = [
            "pytest",
            "pytest -v",
            "python -m pytest tests/",
            "git status",
            "git status --short",
            "git log -n 5 --oneline",
            "git log --format=oneline",
            "npm test",
            "cargo test",
            "python --version",
            "echo 'safe build'",
            "",
            "   ",
        ]
        for cmd in safe_commands:
            # Should execute cleanly without raising PermissionError
            validate_safe_command(cmd)
