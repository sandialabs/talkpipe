""" A command line interface for the talkpipe chat pipeline. 

Let's a user chat with the chat pipeline from the command line.
"""
import argparse
from talkpipe.pipe import io 
from talkpipe.llm import chat

def run_chat_pipeline():
    """Run an interactive chat pipeline with configurable parameters.

    This function sets up and executes a chat pipeline using command line arguments. It allows users to
    configure the system prompt, chat mode (single or multi-turn), model selection, input source, and
    output file options.

    Args:
        None (uses command line arguments)

    Command Line Arguments:
        --system_prompt (str): The system prompt for the chat.
            Default: "You are a helpful and friendly assistant."
        --single_turn (bool): Flag to enable single-turn chat mode.
            Default: False (multi-turn mode)
        --model (str): The language model to use for chat.
            Default: None
        --source (str): How to connect to the model (e.g. ollama).
            Default: None
        --outfile (str): Path to save the chat output as a pickle file.
            Default: None

    Returns:
        None

    """
    parser = argparse.ArgumentParser(description='Run the talkpipe chat pipeline.')
    parser.add_argument('--system_prompt', type=str, default="You are a helpful and friendly assistant.", help='The system prompt for the chat.')
    parser.add_argument('--single_turn', action='store_true', help='Whether the chat is multi-turn.')
    parser.add_argument('--model', type=str, default=None, help='The model to use for the chat.')
    parser.add_argument("--source", type=str, default=None, help="The source of the chat.")
    parser.add_argument("--outfile", type=str, help="The output file for the chat.")
    args = parser.parse_args()

    pipeline = io.Prompt() | chat.LLMPrompt(source=args.source, 
                                          name=args.model, 
                                          system_prompt=args.system_prompt, 
                                          multi_turn=not args.single_turn) | io.Print()
    if args.outfile:
        pipeline = pipeline | io.writePickle(fname=args.outfile)
    pipeline = pipeline.asFunction(single_out=False)
    pipeline()

if __name__ == '__main__':
    run_chat_pipeline()
