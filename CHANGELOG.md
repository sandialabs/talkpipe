# Changelog

## 0.4.2 (in progress)
### New Segments
 - snippet - lets the script writer either load chatterlang code from a file or provide it as a parameter. 
 - Abstracted the comparison filter used for gt and lt
 - Added filters for gte (greater than or equal), lte (less than or equal), eq (equal) and neq (not equal)
### Improvements
 - Reconfigured the Docker containers so that there is a base container with the pre-requisites and one for talkpipe.
 This reduces the time needed to build a talkpipe container if the base already exists.
 - Retooled unit tests to eliminate the "online" fixture, replacing it with something that checks if ollama and mongo are
 available locally and skipping tests that require them if they are not available.
### Bug Fixes
 - Fixed error in rss.py causing a crash if the URL was specified in the configuration file or environment variable
 - Handled code where robots.txt response is returned compressed.  It now decompresses it rather than erroring out.



## 0.4.1
- Updated syntax so that pipelines in forks can contain more than one segment.  This was an oversight in the original design.
- Added the mongoInsert and mongoSearch segments
- Generalized LLM source so that new ones can be registered and used without modifying TalkPipe
- Updated the Embedding API to match the chat api (with sources, etc)
- Added ability to create and reduce matrices using UMAP and t-SNE
- Added template segment for populating a string template
- Update chatterlang so that a double-double quote ("") gets resolved to one double quote
- Fixed bug in extract_property that would cause it to fail seeing some properties
- Improved unit testing and coverage
- Updated the guided generation classes to make it easier to do guided generations problems in talkpipe
- Split the talkpipe.util module into a talkpipe.util subpackage with different modules for different types of utilities.
- Updated the logo
- Improved and refined the wording in the README
- Move the documentation script into apps and added a script so you can generate documentation files when talkpipe is installed

## 0.3.1
- jupyter notebook widgets
- a hash segment

## 0.3.0
- Basic web app for writing and executing ChatterLang scripts, along with endpoints for the underlying functionality.  Includes the ability to:
  - write scripts in a text area and compile/execute them.
  - interactive provide text input to the script if the script requires it.
  - the ability to see logging statements emitted.
  - run the server using a command "chatterlang_server" that is included in the whl file.
  - view documentation for the include sources and segments.  Note that the documentation is rebuilt
  everytime a whl file is generated.
  - view and load various example scripts.
installed.  This works on at least windows and linux
- Added comment support for ChatterLang, anything from a hash mark (#) until the end of the line.
- Added configureLogging segment for configuring logging levels and files from within a script.  This is probably temporary and will be removed before 0.3.0 as a better solution is written.
- Consolidated the logic around configuring logging, migrating the various ways of specifying the configuration strings from runscript into the configure_logging method itself.

## 0.2.2 (2025-02-21)
- The rss segment can get the url to download from the rss_url configuration setting.
- Updated OpenAI source so that it can support guided generation (and thus the llmScore segment)

## 0.2.1 (2025-02-21)
- Catch all ConnectionErrors when downloading the robots.txt file.