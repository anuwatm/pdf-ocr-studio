# Workspace Agent Rules & Safety Policies

## 1. Auto-Approve & File Safety Policy

- **Autonomous Execution (Auto-Approve)**:
  - The agent proceeds autonomously for routine, non-destructive development tasks including:
    - Reading files and inspecting directories
    - Modifying existing files or creating new project files
    - Running build, compile, lint, and test commands (`python -m unittest ...`, `npm run ...`)
    - Investigating codebase and diagnosing issues

- **Mandatory Approval for File Deletion (Strict Safety Gate)**:
  - The agent **MUST NEVER** autonomously delete, purge, or remove files or directories (e.g. via `rm`, `del`, `Remove-Item`, `os.remove`, `os.unlink`, `shutil.rmtree`, or database record wipes) without prior user confirmation.
  - Before performing any deletion:
    1. The agent must clearly list the exact paths or patterns of files/directories intended for removal.
    2. The agent must pause and ask the user for explicit confirmation before executing the deletion.
