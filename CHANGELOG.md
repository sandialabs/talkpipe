# Changelog

## 0.8.1
### Improvements
- change --env to --script in Dockerfile.  This was a change in 0.8.0.
- updated Dockerfile so that the app will not run as root.

## 0.8.0
### New Segments and Sources
- **listFiles** – Takes a path (optionally with wildcards) and emits a stream of file paths (and optionally directory paths).

### Improvements

Note that this release introduces significant API-breaking changes compared with 0.7.x and earlier releases. The software is largely feature-complete for 1.0.0; these releases focus on making the API self-consistent.

- chatterlang_serve
  - Added a `--display-property` parameter to display a specified property as the user message in the stream interface, rather than printing a string version of the whole input JSON (still the default).
  - Fixed a bug causing `/stream` to not respect position directives.
  - The default form now issues a single text item with the property `prompt`.
  - Added a "persist" option to the UI configuration form to specify fields that will not be cleared after each query.
  - Added multi-session support so multiple people can use it at the same time.
  - Added the ability to specify configuration values on the command line that are available to the script (also noted below).
- Added the ability to pass parameters to `chatterlang_script`, `chatterlang_workbench`, and `chatterlang_serve` using the `--` syntax. For example, `--PATH /my/path` will add the value to the configuration at `/my/path`. Example: `python -m talkpipe.app.chatterlang_script --script "INPUT FROM echo[data=$MYPATH] | listFiles | print" --MYPATH "~"`
- Updated the tutorial scripts and the script names in Tutorial 3; moved the examples to the docs directory.
- Updated the unit documentation analyzer to ignore `item` and `items` parameters. These terms are reserved for the data passed into a segment and should not be used as parameters otherwise.
- Updated `chatterlang_workbench` to return a 413 error when a script is longer than 10,000 characters (hard-coded limit).
- Added more comprehensive documentation.
- Removed the `chatcli` application; its functionality is easy to reproduce with `chatterlang_script`.
- Added a `load_script` function in `talkpipe.util.config`, which provides a common way to specify scripts (directly, in a file, in a configuration entry, or via an environment variable) for a consistent experience across applications.
- Across all apps, changed the `--load_module` parameter to `--load-module` for consistency.
- Standardized parameters that refer to model names to `model` rather than `name` or `model_name`.
- Renamed applications for consistency.
- Added the command `chatterlang_reference_browser`, which provides an interactive way to browse the ChatterLang sources and segments.
- Deleted the Jupyter widgets because they were not useful.
- Removed `accelerate` and `pypdf` as dependencies. `accelerate` was left over from an earlier version and is no longer necessary; it added unnecessary bulk.
- When not specified, use default temperature values, and pass the temperature parameter only when explicitly provided; not all models accept a temperature.
- Changed `readtxt` and `readdocx` to `field_segments`.
- Improved unit-test coverage.

## 0.7.1
### New Segments and Sources
 - Added **formatItem** to produce a human-readable text representation of various properties of an item, and added relevant methods to data_manipulation.
 - Added **copy** and **deepcopy** segments for making copies of data in a pipeline. This is important in situations where you 
   don't want the original input data to be modified during processing.

### Improvements
 - Added an "examples" directory with three tutorials, each of which builds on the previous one and contains multiple steps.
 - Updates to **chatterlang_serve**:
  - Changed the default port.
  - Fixed a bug causing it to be unable to load a script from a file.
 - Added metric and method options to vector_search in the SimpleVectorDB class and propagated those through to searchVector.
 - Updated **progressTicks** so it writes to stderr rather than stdout.
 - Updated **searchWhoosh** so the user can specify fields to use as the query and whether to attach results or pass them all along.


## 0.7.0
### New Segments and Sources
 - **progressTicks** – Prints out a tick for every n items seen and a new line for every m ticks.  
  Especially useful for debugging and marking progress in logs.
 - **indexWhoosh** and **searchWhoosh** – Added segments for creating and searching Whoosh
  indices. This provides built-in full-text support in TalkPipe.
 - **addVector** and **searchVector** – Added segments for creating and searching the simple
  built-in vector store.

### Improvements
 - Rewrote firstN to use decorator syntax (making it shorter) and to not throw an exception
  when there are fewer than N items.
 - Created a set of protocols for search engines, both full-text and vector DB-based.  
  These protocols can be used to write wrappers around different search engines and 
  vector databases, providing a common API that can then be used in different segments
  and sources.
 - Integrated the Whoosh pure-Python, stand-alone search engine. This is intended for testing,
  debugging, and smaller stand-alone scenarios. It allows a programmer to work on pipelines that 
  use full-text search engines without setting up a full search engine server. It can support
  tens of thousands of smaller documents. A Python class wrapping Whoosh in a TalkPipe-like
  design pattern is included, as well as segments for indexing and searching.
 - Added SimpleVectorDB, a pure Python, simple vector database. It allows a programmer to build
  and debug pipelines requiring simple vector databases. It supports smaller-scale databases
  that can later be replaced with a separate server.
 - Added a default option to extract_property and propagated the option to several segments.
 - Wrote a conceptual diagram for the library and wrote short descriptions to orient people to 
  how the library can be used.

## 0.6.0
### New Segments and Sources
 - **writeString** – writes items to a file, casting each into a string. Optionally, specify the field to write.
 - **longestStr** – chooses the longest string from among the fields specified. This could be done with a lambda expression,
  but it is needed often enough, and is awkward enough as a lambda expression, that a separate command was written.
 - **sleep** – yields each item and then sleeps for the specified number of seconds.

### Improvements
 - Fixed a bug preventing the OpenAI adapter from working. Removed the OpenAI mockup test and replaced it with a unit test that
  communicates with OpenAI when the unit test environment is properly configured.
 - Updated chatterlang_serve to include a user-facing web app. Allows the user to specify a YAML file to define the format expected by 
  the endpoint. The user can then go to /stream with their browser and get a form where they can enter the data that will be
  converted into JSON and sent to the endpoint. This is in addition to the ability to post to the endpoint directly as before.   
 - Updated writePickle so that it always passes along every item. Also, 
  if writing all items, they are not written to a list, but written
  one by one into the file.
 - Replaced the mocked OpenAI unit test with an actual call to OpenAI, contingent
  upon it being accessible. Fixed the OpenAI prompt adapter.
 - Added an optional field specifier to writePickle.
 - Added the ability for chatterlang_serve and chatterlang_workbench to load custom modules.
 - Removed **call_func**. This is superseded by the more flexible lambda.


## 0.5.0
### New Segments and Sources
 - lambda expression integration
   - **lambda** - lets one write lambda expressions with limited, but common data manipulation segments.  This will
  eliminate the need for most small, simple segments, even gt, lt, etc.
   - **lambdaFilter** - filters based on a lambda expression.  Uses the same syntax as lambda.
  - **readEmail** - source for reading email from an IMAP server, along with helper functions
  - **sign** and **verify** for signing and verifying data.  Also added utility functions for creating keys and associated 
   functions.
 - **jsonReceiver** - both a source and an app for opening an endpoint that can receive json and pass it through a 
 chatterlang script

### Improvements
 - Broad support for configuration and environment variables.  When a parameter to a segment or source starts with a dollar sign (e.g. $myval),
 the system will look first in the current configuration for the key "myval" and then in the OS' environment variables for TALKPIPE_myval.
 - Added a safe lambda expression compiler to data_manipulation.  Enables only basic data manipulation functionality
 - Use can specify custom user-agent strings via a configuration file or environment variable for web page
 downloader.
 - Renamed threading.py to thread_ops.py to avoid name collision
 - Renamed scriptendpoint.py to chatterlang_workbench.py for clarity
 - Documentation improvements
 - Moved code closing mongo connections to the end of the internal loop and out of the del code.  It was causing 
error when being disposed as python was exiting.
 - Changed n_iter to max_iter to resolve warning with tsne.
 - Adjust n_neighbors in umap when larger than the number of points to resolve warning
 - Added chatterlang_scipt to the package installer so the user can run talkpipe.app.chatterlang_script from the commandline

## 0.4.2 
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
  - run the server using a command "chatterlang_workbench" that is included in the whl file.
  - view documentation for the include sources and segments.  Note that the documentation is rebuilt
  everytime a whl file is generated.
  - view and load various example scripts.
installed.  This works on at least windows and linux
- Added comment support for ChatterLang, anything from a hash mark (#) until the end of the line.
- Added configureLogging segment for configuring logging levels and files from within a script.  This is probably temporary and will be removed before 0.3.0 as a better solution is written.
- Consolidated the logic around configuring logging, migrating the various ways of specifying the configuration strings from chatterlang_script into the configure_logging method itself.

## 0.2.2 (2025-02-21)
- The rss segment can get the url to download from the rss_url configuration setting.
- Updated OpenAI source so that it can support guided generation (and thus the llmScore segment)

## 0.2.1 (2025-02-21)
- Catch all ConnectionErrors when downloading the robots.txt file.
