## Project Overview
TalkPipe is a Python toolkit that makes it easy to create, test, and deploy workflows that integrate Generative AI with your existing tools and data sources. TalkPipe treats LLMs as one tool in your arsenal - letting you build practical solutions that combine AI with data processing, file handling, and more.  

- **Chat with LLMs** - Create multi-turn conversations with OpenAI or Ollama models in just 2 lines of code
- **Process Documents** - Extract text from PDFs, analyze research papers, score content relevance
- **Analyze Web Content** - Download web pages (respecting robots.txt), extract readable text, and summarize
- **Build Data Pipelines** - Chain together data transformations, filtering, and analysis with Unix-like simplicity
- **Create AI Agents** - Build agents that can debate topics, evaluate streams of documents, or monitor RSS feeds
- **Deploy Anywhere** - Run in Jupyter notebooks, as Docker containers, or as standalone Python applications

## Development Guidelines 
pytest unit tests are under tests/
the code for the library is under src/
The core pipe API classes and code is under talkpipe/pipe
ChatterLang is an external DSL and is defined under talkpipe/chatterlang
Other packages in the project other than util include implementations of pipe sources and segments
Util contains various generally usable utility functions, expecially for basic data manipulation and configuration.
talkpipe/README.md contains a longer overview

## Important Commands
python -m build for creating a new release
pytest --cov=src for unit test coverage
