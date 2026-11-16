# CSU (CodeStudioUniversial)

A minimal desktop code editor built with Python and tkinter.

## Features

- Project tree panel: open a folder, browse files and subfolders
- Create, rename, and delete files and folders (supports nested paths like `folder/folder/file.ext`)
- Tabbed editor with closable tabs
- Line numbers and syntax highlighting (via `pygments`, with a built-in regex-based fallback if it's not installed)
- Edit, select all, copy, cut, paste, undo/redo (`Ctrl+S` to save)
- Run the current file in a new console window (`F5`)
- Remembers the last opened project in `%APPDATA%/CSU/config.json` (or `~/.config/CSU` on Linux/macOS)
