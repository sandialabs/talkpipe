# TalkPipe developer handbook

Contributor-oriented reference: glossary, repository conventions, parameter semantics, and standard configuration keys.

## Glossary

* **Unit** - A component in a pipeline that either produces or processes data.  There are two types of units: Sources and Segments.
* **Segment** - A unit that reads from another Unit and may or may not yield data of its own.  All units that
are not at the start of a pipeline are Segments.
* **Source** - A unit that takes nothing as input and yields data items.  These Units are used in the
"INPUT FROM..." portion of a pipeline.

## Conventions

### Versioning

This codebase will use [semantic versioning](https://semver.org/) with the additional convention that during the 0.x.y development that each MINOR version will mostly maintain backward compatibility and PATCH versions will include substantial new capability.  So, for example, every 0.2.x version will be mostly backward compatible, but 0.3.0 might contain code reorganization.

### Codebase Structure

The following are the main breakdown of the codebase. These should be considered firm but not strict breakdowns. Sometimes a source could fit within either operations or data, for example.

* **talkpipe.app** - Contains the primary runnable applications.
  * Example: chatterlang_script
* **talkpipe.operations** - Contains general algorithm implementations.  Associated segments and sources can be included next to the algorithm implementations, but the algorithms themselves should also work stand-alone.
  * Example: bloom filters
* **talkpipe.data** - Contains components having to do with complex, type-specific data manipulation.
  * Example: extracting text from files.
* **talkpipe.llm** - Contains the abstract classes and implementations for accessing LLMs, both code for accessing specific LLMs and code for doing prompting.
  * Example: Code for talking with Ollama or OpenAI
* **talkpipe.pipe** - Code that implements the core classes and decorators for the pipe api as well and misc implementations of helper segments and sources.
  * Example: echo and the definition of the @segment decorator
* **talkpipe.chatterlang** - The definition, parsers, and compiler for the chatterlang language as well as any chatterlang specific segments and sources
  * Example: the chatterlang compiler and the variable segment

### Source/Segment Names

- **For your own Units, do whatever you want!** These conventions are for authors writing units intended for broader reuse.
- **Classes that implement Units** are named in CamelCase with the initial letter in uppercase.
- **Units defined using `@segment` and `@source` decorators** should be named in camelCase with an initial lowercase letter.
- In **ChatterLang**, sources and segments also use camelCase with an initial lowercase letter.
- Except for the **`cast`** segment, segments that convert data into a specific format—whether they process items one-by-one or drain the entire input—should be named using the form `[tT]oX`, where **X** is the output data type (e.g., `toDataFrame` outputs a pandas DataFrame).
- **Segments that write files** use the form `[Ww]riteX`, where **X** is the file type (e.g., `writeExcel` writes an Excel file, `writePickle` writes a pickle file).
- **Segments that read files** use the form `[Rr]eadX`, where **X** is the file type (e.g., `readExcel` should read an Excel file).
- **Parameter names in segments** should be in all lower case with words separated by an underscore (_)

### Parameter Names

These parameter names should behave consistently across all units:

- **item** should be used in field_segment, referring to the item passed to the function.  It will not
  be a parameter to the segment in ChatterLang.

- **items** are used in segment definitions, referring to the iterable over all the pieces of data in the stream.
  It will not be a parameter used anywhere as a parameter in ChatterLang.

- **set_as**
  If used, any processed output is attached to the original data using bracket notation. The original item is then emitted.

- **fail_on_error**
  If True, the exception should be raised, likely aborting the pipeline.  If False, the operation should continue
  and either None should be yielded or nothing, depending on the segment or source.  A warning message should be logged.

- **field**
  Specifies that the unit should operate on data accessed via “field syntax.” This syntax can include indices, properties, or parameter-free methods, separated by periods.
  - For example, given `{"X": ["a", "b", ["c", "d"]]}`, the field `"X.2.0"` refers to `"c"`.

- **field_list**
  Specifies that a list of fields can or should be provided, with each field separated
  by a comma.  In some cases, each field needs to be mapped to some other name.  In
  those cases, the field and name should be separated by a colon.  In field_lists,
  the underscore (_) refers to the item as a whole.
  - For example, "X.2.0:SomeName,X.1:SomeOtherName".  If no "name" is provided,
  the fieldname itself is used.  Where only a list of fields is needed and no names,
  the names can still be provided but have no effect.

### General Behavior Principles

* Units that have side effects (e.g. writing data to a disk) should generally also pass
on their data.

### Source and Segment Reference

The chatterlang_workbench command starts a web service designed for experimentation.  It also contains links to HTML and text versions
of all the sources and segments included in TalkPipe.

After talkpipe is installed, a script called "chatterlang_reference_browser" is available that provides an interactive command-line search and exploration of sources and segments.  The command "chatterlang_reference_generator" will generate single page HTML and text versions of all the source and segment documentation.

### Standard Configuration File Items

Configuration constants can be defined either in ~/.talkpipe.toml or in environment variables.  Any constant defined in an environment variable needs to be prefixed with TALKPIPE_.  So email_password, stored in an environment variable, needs to be TALKPIPE_email_password.  Note that in ChatterLang, any key defined in ~/.talkpipe.toml or set via a TALKPIPE_* environment variable can be referenced in scripts as a parameter using $var_name.  That reference resolves to the environment variable TALKPIPE_var_name or to var_name in talkpipe.toml.

* **default_embedding_model_source** - The default source (e.g. ollama) to be used for creating sentence embeddings.
* **default_embedding_model_name** - The name of the LLM model to be used for creating sentence embeddings.
* **default_model_name** - The default name of a LLM model to be used in chat
* **default_model_source** - The default source (e.g. ollama) to be used in chat
* **email_password** - Password for the SMTP server
* **logger_files** - Files to store logs, in the form logger1:fname1,logger2:fname2,...
* **logger_levels** - Logger levels in the form logger1:level1,logger2:level2
* **recipient_email** - Who should receive a sent email
* **rss_url** - The default URL used by the rss segment
* **sender_email** - Who the sender of an email should be
* **smtp_port** - SMTP server port
* **smtp_server** - SMTP server hostname

---

*For the main project overview, see the [project README](../../README.md).*
