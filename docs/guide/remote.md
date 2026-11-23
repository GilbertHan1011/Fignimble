# Projects on an SSH server

When a project's data and Python environment are on a Linux server, Fignimble can edit it from your Mac. The figures
are drawn on the server, by its Python, next to its data. The window on the Mac works as it does for a local project.

**File ▸ Open Project on SSH Server…** (<kbd>⇧</kbd><kbd>⌘</kbd><kbd>O</kbd>) asks for three things:

- **Server**: a `Host` from `~/.ssh/config`, or `user@server`.
- **Folder**: the project's folder there. **List** shows the folder's contents, and double-clicking a folder goes into
  it. **Open** opens the folder that is listed.
- **Python there**: the Python that draws the figures. It needs Python 3.10 or newer with matplotlib, pymupdf and
  pillow, plus whatever the panels' code imports. Give the full path of an environment's Python, for example
  `~/miniconda3/envs/analysis/bin/python`, because ssh doesn't run your shell's start-up files. The field remembers
  the last value for each server.

The project then appears under **File ▸ Open Recent** with the other projects.

## How it works

Fignimble starts its engine on the server over one ssh connection. The first time, and again after each Fignimble
update, it copies the engine (under 1 MB) to `~/.cache/fignimble/engine/` there. Nothing is installed with pip, and
nothing outside that folder changes.

The Mac keeps a mirror of the project's code, tables and pictures in `~/Library/Caches/Fignimble/remote/`. Fignimble
keeps the mirror and the server in step:

- Canvas edits are written into the code on the server. The mirror has the new code before the canvas updates.
- Changes made on the server, by you or an agent in the terminal, reach the mirror within a second or so.
- Files changed in the mirror, from the code pane or an editor opened with **Open in…**, go to the server within a
  second.
- If a file changed on both sides, the server's version wins. The Mac's copy is saved in the `.conflicts` folder
  next to the mirror.

Data files (anything that isn't code, a table, a note or a picture, or that is larger than 8 MB) stay on the server.
Panels read them there, as they always have.

The terminal tabs are ssh sessions in the project's folder on the server. Unlike the engine, they can ask for a
password. A picture you place from the Mac is copied into the project's `images/` folder on the server. Exports are
written on the server and then copied to wherever you chose on the Mac.

## Connecting

ssh can't ask for a password here, so the server must accept one of these:

- your key (`ssh-copy-id server` sets this up);
- a key held by an ssh-agent;
- a connection you already opened in a terminal, with `ControlMaster` set in `~/.ssh/config`. This is also the way to
  use servers that need two-factor login. It makes connecting faster, too:

```
Host lab
    HostName lab.example.org
    ControlMaster auto
    ControlPath ~/.ssh/cm-%C
    ControlPersist 4h
```

If the connection drops, Fignimble says so. Open the project again from **File ▸ Open Recent**. Edits that had
not reached the server yet are still in the mirror, and are sent when you reconnect.

## Fonts

The server draws the text, using its own fonts. Many Linux servers don't have Arial or Helvetica, so matplotlib
substitutes another font without saying so. If the text on the canvas looks wrong, install the fonts on the
server, or put `.ttf` files in `~/.fonts` there and delete `~/.cache/matplotlib`.
