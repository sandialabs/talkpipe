# Changelog

## In Development
- Added a backward compatible metadata capability.  By default metadata information
  passes through the stream without being passed to segments.  But if a segment wants
  to process metadata, it can so declare when being defined and metadata will be passed
  to it during processing.  This capability will support things like issuing period flush
  commands during processing.
- Added `AdaptiveBuffer` in `talkpipe.util.collections` for rate-aware buffering that
  returns buffered batches when it decides to flush, adjusting between single-item and
  batch handling.
- Updated `addToLanceDB` to use `AdaptiveBuffer` for adaptive batching instead of a
  fixed-size cache.  If documents are coming slowly, they will get added one by one,
  scaling up to batch_size as the rate increases.
- Updated lance and whoose segments to be responsive to Flush metadata.
- Added new arrow-based forking syntax in ChatterLang for connecting pipelines to forks.
  Pipelines can now use `-> fork_name` to feed into a fork and `fork_name ->` to read from
  a fork, providing a more intuitive way to express producer-consumer relationships in
  complex workflows. The implementation uses `networkx` for graph structure management,
  replacing manual adjacency list tracking with a cleaner `DiGraph` representation.
- Improved documentation consistency and accuracy:
  - Added metadata stream documentation to architecture index for better discoverability
  - Removed references to non-existent `unwrap_metadata()` function from metadata-stream.md
  - Enhanced RuntimeComponent documentation to include `add_constants()` method

## 0.11.0

### New Features
- Added fileDelete segment for deleting files in a pipline after they have been processed.
- Added fileExistsFilter segment for filtering out paths that can't be resolved.
- Added debounce segment.  This is a filter that looks for a key and emits one item with
  that key after it stops seeing the key for a specified time.  Originally written for 
  emitting file events after a file is done changing.
- Added a diagPrint segment that prints information about items passing through the pipline
  This can be placed between segments and sources to help debug more complex pipelines.
- Added diagPrint segments among each step in the pipelines package with output set to
  None by default.


### Improvements
- Significant, API breaking refactor to `extraction.py` and how file extraction is done.
  Added `ExtractorRegistry` class for managing file text extractors.
  The registry maps file extensions to extractor callables and supports a default extractor
  for unregistered extensions. Extractors are now generators that yield strings, allowing
  multi-record file formats (CSV, JSONL) to emit multiple items per file. `ReadFile` is now
  a multi-emit segment using `global_extractor_registry` by default. Unsupported files are
  skipped (yield nothing) by default; pass `skip_unsupported=False` to raise exceptions.
  Added standalone extractor functions (`extract_text`, `extract_docx`, `skip_file`),
  `get_default_registry()` factory, and `global_extractor_registry` instance.
- Added `role_map` parameter to LLM prompt adapters (Ollama, OpenAI, Anthropic) for setting up
  initial conversation context with pre-defined role messages.
- Added `ExtractionResult` Pydantic model with `content`, `source`, `id`, and `title` fields.
  `ExtractorFunc` now yields `ExtractionResult` objects instead of raw strings, giving
  extractors full control over metadata. `ReadFile`, `readtxt`, and `readdocx` yield
  `ExtractionResult` objects. For multi-emit extractions, extractors should include an
  index suffix in the `id` field (e.g., `source:1`, `source:2`) to ensure uniqueness,
  and should set descriptive `title` values (e.g., `filename:line1`). The model uses
  `extra="allow"` to permit additional fields to be added by downstream segments.
- Allow for silently failing (with a log message) when an embedding fails. Fixed a bug where
  `embedder.execute()` was called twice, once inside a try-except block and once outside,
  causing errors to be raised even when `fail_on_error=False`.  
- Improved documentation and added github copilot instructions
- Removed `memory://` support from LanceDB integrations. Use `tmp://<name>` for process-scoped 
  temporary databases or filesystem paths for persistence. Updated `parse_db_path` to reject 
  `memory://`, refreshed docstrings, and migrated tests to `tmp://` URIs.

## 0.10.2

### Improvements
- Added `system_prompt` parameter to RAG pipeline segments (**ragToText**, **ragToBinaryAnswer**, **ragToScore**).
  Users can now customize the system prompt sent to the completion LLM. Each segment type has an
  appropriate default: **ragToText** uses a prompt that emphasizes grounding responses in provided context,
  while **ragToBinaryAnswer** and **ragToScore** use prompts tailored to their respective output formats.
- Added `table_name` parameter to **ragToText**, **ragToBinaryAnswer**, and **ragToScore** segments.
  Users can now specify which LanceDB table to search, enabling multiple knowledge bases within the same database.
  Defaults to "docs" for backward compatibility.
- Added optional paragraph number tracking to **shingleText** segment via `emit_detail` parameter.
  When enabled, returns dictionaries with `text`, `first_paragraph`, and `last_paragraph` keys instead of just text strings.
  This enables tracking of which source paragraphs contributed to each shingle. Defaults to False for backward compatibility.
- Extended **flatten** to be a multi-emit field segment so it can flatten fields in an object and return the whole object
  with individual components.
- Made **readJsonl** a field segment so it can get the filename from a field and assign each read line back into another field.
- Added `embedding_prompt` parameter to basic RAG pipelines for custom embedding prompts.
- Added `history` parameter to **prompt** source to support saving/loading command history from a file. Set to None by default for backward compatibility.
- Fixed bug in **shingleText** where incomplete shingles would not be emitted when `overlap > 0` if no complete
  shingle was ever produced for a given key. Now ensures that documents with only incomplete data still produce output,
  and that all chunks are properly covered when using count mode with overlap.
- Fixed incorrect name in default embedding model configuration key. Moved constants to the constants module.
- Reviewed, condensed, and improved documentation.

## 0.10.1
### New Features
- Added get_process_temp_dir() utility to allow creation of temporary directories that are removed
  when the process exists using `atexit`, but are consistent withing. aprocess. 
- Added array parameter support in ChatterLang syntax. Segments and sources can now accept array
  parameters using bracket notation, e.g., `my_segment[arr=[1, "str", MY_CONST]]`. Arrays support
  mixed types (strings, numbers, booleans, identifiers), nested arrays, and constant resolution
  within array elements.

### Improvements
- Fixed discrepencies in documentation
- Added upsert support to **addToLanceDB** segment. By default, documents with the same ID are now
  updated instead of raising an error, matching the behavior of **indexWhoosh**. Set `upsert=False`
  to restore the previous behavior of raising an error on duplicate IDs. Also added `upsert_vector()`
  method to `LanceDBDocumentStore` class.
- Added `assign_property()` utility function to `data_manipulation.py` that provides a unified interface
  for assigning values to both dictionary-like objects (using bracket notation) and regular objects
  including pydantic models (using setattr). This mirrors the existing `extract_property()` function
  for reading values.
- Updated **setAs** segment and all segments with `set_as` parameter to support pydantic models and
  other objects in addition to dictionaries. This includes segments across the codebase: basic.py
  (assign, concat, longestStr, isIn, isNotIn, isTrue, isFalse, Hash), core.py (AbstractFieldSegment),
  search modules (whoosh.py, lancedb.py), llm modules (chat.py, embedding.py), data modules
  (mongo.py, text/chunking_units.py), and pipelines (basic_rag.py, vector_databases.py).
- Added support for `tmp://name` URI scheme in LanceDB path parameters. This enables process-scoped
  temporary databases that are automatically cleaned up on exit. Temporary databases with the same name
  share state within a process, making them ideal for testing or ephemeral workflows. Implemented via
  `get_process_temp_dir()`.
- Added initial claude code commands for reviewing documentation.

## 0.10.0
### New Features
- Added **splitText** segment to split strings either by length or by delimiter. Now available as an entry point.
- Added **shingleText** segment for creating overlapping n-grams (shingles) from text with support for key-based grouping and configurable overlap. Now available as an entry point.
- Added **extractProperty** segment that extracts properties using the same methodology as a the
  property designator in a field list.
- Added **makeVectorDatabase** segment to create vector databases in LanceDB by embedding documents
  and storing them with their metadata. Supports custom embedding models, table names, document IDs,
  and overwrite options.
- Added **searchVectorDatabase** segment to search vector databases in LanceDB. Accepts either string
  queries or dictionary inputs with a query field. Search results can be yielded directly or attached
  to the input item. Supports custom embedding models, result limits, and read consistency intervals.
- Added **ragToText** end-to-end RAG pipeline convenience segment that combines vector database search,
  prompt construction, and LLM completion into a single pipeline. Automatically retrieves relevant
  documents from a vector database, constructs a RAG prompt with background context, and generates
  completions using the specified LLM. Supports configurable prompt directives, result limits, and
  field assignments.
- Added **ragToBinaryAnswer** RAG pipeline segment that outputs structured binary (yes/no) answers
  with explanations from an LLM. Similar to ragToText but uses guided generation to ensure responses
  follow a boolean answer format with justification.
- Added **ragToScore** RAG pipeline segment that outputs structured integer scores with explanations
  from an LLM. Useful for relevance scoring, quality assessment, and other evaluation tasks where
  numeric ratings are needed along with reasoning.
- Added comprehensive unit tests for RAGToBinaryAnswer and RAGToScore segments, covering basic
  functionality, field operations, multiple queries, and edge cases.

### Breaking Changes
- Removed deprecated **simplevectordb** module. Users should migrate to **LanceDBDocumentStore** from
  `talkpipe.search.lancedb`, which provides equivalent functionality with improved performance.
- Removed deprecated **reduceUMAP** segment and `umap-learn` dependency. Users should migrate to
  **reduceTSNE** or other dimensionality reduction methods.
- Removed `numba` dependency as it was only required by the removed `umap-learn` package.

### Improvements
- Updated README.md Example 5 (RAG Pipeline with Vector Database) to use standalone data instead
  of relying on external txt files. The example now defines documents as inline strings and uses
  **toDict** to convert them to dictionaries, making it fully self-contained and easier to run.
- Added an option n to sleep so that it can be configured to sleep every n items rather than
  every item.
- Extended AbstractFieldSegment and the field_segment decorator to support segments that return
  more than one item per input item.  If set_as is specified, the outer object is shallow copied
  for each output and the output is set appropriately.
- Added a new registry system with configurable lazy loading via `LAZY_IMPORT` setting. When enabled,
  provides an 18-fold performance improvement (from 2.9s to 0.16s in testing) by deferring module
  imports until needed. The default behavior remains unchanged for compatibility. Added comprehensive
  documentation for the lazy loading feature in `docs/api-reference/lazy-loading.md`,
  covering configuration, performance characteristics, usage examples, and best practices for module
  organization and plugin development.
- Fixed security issue in `src/talkpipe/chatterlang/registry.py` where exceptions were being silently
  ignored (Bandit B110). Replaced bare `except Exception: pass` blocks with proper logging statements
  to aid in debugging and follow security best practices.
- Added `requires_package_installed` pytest fixture to gracefully skip entry point tests when the
  package is not installed (e.g., before running `pip install -e .`). Tests now provide clear skip
  messages instead of failing with confusing errors. This makes the test suite more developer-friendly
  for new contributors and CI environments.
- Updated README.md section 2 (ChatterLang External DSL) to demonstrate how to register custom
  components using `@registry.register_segment()`. The example shows how to take the `uppercase`
  segment from section 1 (Pipe API) and make it available in ChatterLang scripts, with working
  code that demonstrates compilation and execution.
- Added documentation links to all built-in application commands in README.md "Key Applications"
  and "Built-in Applications" sections, making it easier for users to find detailed documentation
  for each command-line tool.
- Enhanced `extract_property` to support `_` as a passthrough/no-op in dotted property paths. The `_`
  character now acts as an identity operation when used within a path. For example, `"X._"` is
  equivalent to `"X"`, `"X._.1"` is equivalent to `"X.1"`, and `"_.1"` is equivalent to `"1"`. This
  makes it easier to construct dynamic property paths where some components may need to reference the
  current object without changing the navigation level.

## 0.9.4
### Improvements
- Changes several logging statements to make the consistent with the rest of the code
- Refactored **lambda** to use AbstractFieldSegment for consistency
- Removed fail_on_error parameter in **lambda** and **lambdaFilter**.  This is an API breaking change.
  The segments will now always fail on an error and there is no option to silently fail.
- Changed chatterlang_serve so that it raises and exception an exits if given a script that can't be
  compiled.  The previous behavior was that it would issue a log message and fall back to the default
  script.
- Added unit test for parse_unknown_args and expanded it to support boolean flag parameters
- Marked UMAP as deprecated.  It will be removed in 1.0.  It requires additional dependencies that no
  other core modules need.
- Updated the ollama embedding and chat connector so that it uses the OLLAMA_SERVER_URL configuration
  variable as the host where ollama is installed.  So OLLAMA_SERVER_URL can be set in the TOML configuration
  file or TALKPIPE_OLLAMA_SERVER_URL can be set as an environment variable.
- Implemented better compile errors for when sources or segments are not found.  It had been a key error.
  It will now be a compile error.
- Added batch files for the tutorials so it is easier to run them on Windows
- Enhanced **prompt** source to catch downstream pipeline errors and continue prompting instead of
  crashing. When a user enters invalid input that causes an exception in downstream segments, the error
  is displayed with a full traceback, and the prompt continues accepting input. This makes interactive
  pipelines more robust and user-friendly. The error-resilient behavior is enabled by default but can
  be disabled by setting `error_resilient=False`.
- Updated **chatterlang_serve** to support API key configuration via the configuration system. When
  `--api-key` is not specified on the command line, it will check for `API_KEY` in the configuration,
  which automatically checks the `TALKPIPE_API_KEY` environment variable. This makes it easier to
  deploy chatterlang_serve in Docker and CI/CD environments without exposing API keys in command history.
- Added support for single-quoted strings in ChatterLang scripts. Single quotes work identically to
  double quotes, including support for escaping quotes by doubling them (`''` → `'`). This provides
  more flexibility when writing scripts, especially when the string content contains double quotes.
- Enhanced **echo** source with an `n` parameter to repeat the output data multiple times. For example,
  `echo[data='a,b', n=3]` will emit: a, b, a, b, a, b. This is useful for testing pipelines and
  generating repeated test data.
- Improved **chatterlang_serve** startup output to clearly distinguish between the user interface URL
  and the API endpoint URL. The server now displays a formatted message showing both URLs with clear
  labels when it starts.
- Updated tutorial 1, step 1 to show more feedback to the user so it doesn't just seem to be hanging

## 0.9.3 
### Improvements
- Updated tutorials to use lancedb.  
- Moved tutorial scripts out of shell scripts into their own files
- Fixed issue with Docker container not including all optional installation components
- Fixed string encoding issue with web page downloads
- Updated documentation for plugins to fix error
- Removed invalid script in pyproject.toml

## 0.9.2
### Improvements
- Added ability for sources and segments to have multiple names in chatterlang.
- Removed signature segments.
- Added Anthropic as a chat provider.
- Updated the install options so that not all the providers have to be installed. Include the provider
you want as a parameter (e.g. pip install talkpipe[anthropic]). Current options are anthropic, openai,
and ollama. Use "all" to install all three.

## 0.9.1
Forgot to import the lancedb module in talkpipe/__init__.py, so it wasn't registering the segments.

## 0.9.0
### New and Updated Segments and Sources
- Added **set**, which simply assigns some constant to a key.
- Added **isTrue** and **isFalse** segments that can function as both a filter or an evaluation of a field.
- Added **llmBinaryAnswer** segment for coercing true/false answers from an LLM.
- Added **searchLanceDB** and **addToLanceDB** for creating and searching LanceDB vector databases. This 
  involved creating a **LanceDBDocumentStore** class that operates in ways compatible with simplevectordb and
  whoosh.
- Renamed **extractor** to **readFile**.

### Improvements
- Configured CI/CD system for GitHub to run tests, security checks, and container builds.
- Fixed identified security vulnerabilities.
- Renamed append_as to set_as and appendAs to setAs throughout the codebase. "Set" is more accurate than "append" for the associated behavior.
- Changed asFunction to as_function.
- Added a check and throw an exception in simplevectordb if the user has clustered and then tries to use cosine for search.
- Added a plugin system so it is easier for external whl files to add commands to chatterlang.
- Refactored the documentation system:
  - Pulls from the registry in real time. This ensures that plugin commands are 
    included in the documentation system. It also reduces potential problems from bad parsing of source code.
  - Pulls "Annotated" typing from parameter names to create the Parameters section of the documentation.
    Makes for cleaner, more consistently up-to-date documentation. The use of Annotated is optional.
- Updated **isIn** and **isNotIn** to function like **isTrue** so that they need not always be filters.
- Created an AbstractFieldSegment class and changed the field_segment decorator to use it. This makes it easier
  to create segments with consistent "field_segment" behavior but require additional initialization.
- Renamed ExtractFile to ReadFile and refactored it to be descended from AbstractFieldSegment.
- Renamed **extract** to **readFile** in chatterlang for consistency.
- Deprecated simplevectordb classes and segments. These will be removed in 1.0.0. The lancedb vector database
  provides equivalent functionality and doesn't require all the data to be in memory at once.
- Added an **AbstractFieldSegment** class and refactored **field_segment** to use it. This is so classes can be
  implemented with field_segment functionality that also need some one-time initialization.

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
