# gncgit

gncgit is a minimal Git-like version control system written in Python.

My goal with this project is to understand how version control systems work internally by building one from scratch.

## Current features

* Initialize a repository with `.gncgit`
* Add files to the index
* Store file contents as hashed objects
* Create commits with parent references
* Track the latest commit for each branch
* Checkout branches and restore files from committed objects

## Commands

```bash
gncgit init
gncgit add <file>
gncgit commit -m "<message>"
gncgit checkout <branch>
```

## Internal structure

```txt
.gncgit/
  HEAD
  index.json
  objects/
  commits/
  refs/
    heads/
      main
```

## Project status

This is an early MVP. The current version focuses on the core ideas behind Git: objects, commits, branches, checkout, and the index.

Planned features:

* log
* status
* better checkout behavior
* restore files from specific commits
* branch listing