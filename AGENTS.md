## Dev environment tips
- When running code or pytest, use the .venv environment in the root of the project.
- If the .venv environment doesn't exist and you need to run code or tests, abort and ask the user to create the environment.

## Project Overview
TalkPipe is a Python toolkit that makes it easy to create, test, and deploy workflows that integrate Generative AI with your existing tools and data sources. TalkPipe treats LLMs as one tool in your arsenal - letting you build practical solutions that combine AI with data processing, file handling, and more.  

- **Chat with LLMs** - Create multi-turn conversations with OpenAI, Ollama, or Anthropic models in just 2 lines of code
- **Process Documents** - Extract text from PDFs, analyze research papers, score content relevance
- **Analyze Web Content** - Download web pages (respecting robots.txt), extract readable text, and summarize
- **Build Data Pipelines** - Chain together data transformations, filtering, and analysis with Unix-like simplicity
- **Create AI Agents** - Build agents that can debate topics, evaluate streams of documents, or monitor RSS feeds
- **Deploy Anywhere** - Run in Jupyter notebooks, as Docker containers, or as standalone Python applications

## Project Structure
- talkpipe/app - contains runnable applications
- talkpipe/chatterlang - contains definitions for the chatterlang external DSL built on top of talkpipe/pipe
- talkpipe/data - contains basic data manipulation utilities
- talkpipe/llm - contains chat and embedding utilities
- talkpipe/operations - contains basic operations for chatterlang
- talkpipe/pipe - contains a mix of basic definitions creating the internal DSL
- talkpipe/search - contains data storage and retrieval definitions, including vector databases and full text search
- talkpipe/util - contains utility functions such as configuration and operations system related operations

## Development Guidelines 
- Do not automatically agree.  Question assumptions and point out weaknesses in logic or inconsistences with the rest of the codebase.
- pytest unit tests are under tests/
- the code for the library is under src/
- The core pipe API classes and code is under talkpipe/pipe
- ChatterLang is an external DSL and is defined under talkpipe/chatterlang
- Other packages in the project other than util include implementations of pipe sources and segments
- Util contains various generally usable utility functions, expecially for basic data manipulation and configuration.
- talkpipe/README.md contains a longer overview
- After implementing a new feature, update CHANGELOG.md. Check if an existing entry should be udpated rather than creating a new entry. 
- After making a minor change to an existing feature,  check if the unreleased section of the changelog already mentions the feature. If so, update that changelog entry.  If not, write a new entry in the changelog.
- When making a change, write a unit test that fails without the change or update an existing test, verify that the unit test fails, make the change and then verity that the unit test now passes.  Notify the user if it is not reasonable to write the unit test. 
- When writing unit tests, update and augment existing unit tests is possible and appropriate rather than writing new unit tests.
- Unit tests should be as short as possible while still testing the functionality as completely as possible.
- User interfaces should be visually appealing and maintain consistency with each other.
- When writing or updating pipeline examples in documentation, write examples with stand-alone code and 
    test the examples by running them.
- When creating a new source or segment, update pyproject.toml to include it in the endpoints.
docs/architecture/protocol.md names protocol conventions to use when writing new sources and segments.
- When writing documentation for segments or sources, do not document the parameters.
- When writing new sources or segments, use Annotated in the parameter lists to explain the type and purpose of each parameter.


## Important Commands
python -m build for creating a new release
pytest --cov=src for unit test coverage
