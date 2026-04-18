"""Program entrypoint for the SQL-to-Confluence tool.

This file is invoked directly by CLI commands and GitHub workflow steps.
It delegates execution to cli.main().
"""

from cli import main


if __name__ == "__main__":
    main()
