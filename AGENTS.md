# Codex Instructions

When modifying code in this repo, verify the touched behavior by running the closest real production path available.

Prefer existing tests and app commands when they already cover the behavior. Codex may create temporary, uncommitted verification scripts under `./codex-scripts/` to run the real project code with realistic inputs and check observed behavior.

Use UI automation, Browser Use, or Computer Use for UI/end-to-end behavior when that is the closest real path. Report the command/tool run and the behavior observed.

Do not commit files under `./codex-scripts/`.
