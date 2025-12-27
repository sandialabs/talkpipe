from greenlet import greenlet

def bypass(iterable, predicate, handler):
    """
    iterable:  input iterable
    predicate: function(item) -> bool
    handler:   function(iterator_of_failed_items) -> iterator

    Behavior:
      - Items with predicate(item) == True are yielded directly (bypassed).
      - Items with predicate(item) == False are sent to `handler`, which is
        called exactly once with a single iterator over the failed items.
      - The outputs of `handler` are interleaved with bypassed items in the
        order implied by the original stream.
    """
    it = iter(iterable)
    outer_gl = greenlet.getcurrent()
    first_failed = None
    first_failed_pending = False

    # This greenlet will run the handler
    def handler_runner():
        # Iterator of failed items, implemented cooperatively
        class FailedStream:
            def __iter__(self):
                return self

            def __next__(self):
                # Ask outer for the next failed item
                msg_type, value = outer_gl.switch(("need_item", None))
                if msg_type == "item":
                    return value
                elif msg_type == "end":
                    raise StopIteration
                else:
                    raise RuntimeError(f"Unexpected message to stream: {msg_type}")

        stream = FailedStream()

        # Run the handler; send its outputs to outer
        for out in handler(stream):
            outer_gl.switch(("output", out))

        # Signal completion
        outer_gl.switch(("handler_done", None))

    handler_gl = None

    # Phase 1: yield bypassed items until we see the first failed one
    for item in it:
        if predicate(item):
            # Pass through
            yield item
        else:
            # First failed item: start handler
            first_failed = item
            first_failed_pending = True
            handler_gl = greenlet(handler_runner)
            break

    # If no failing items, we're done (handler never runs)
    if handler_gl is None:
        return

    # Kick off the handler; it will immediately request the first failed item
    msg_type, payload = handler_gl.switch()

    # Main cooperative loop
    while True:
        if msg_type == "need_item":
            # Handler (via FailedStream.__next__) wants the next failed item
            if first_failed_pending:
                # Supply the very first failed item
                next_failed = first_failed
                first_failed_pending = False
            else:
                # Scan the underlying iterator until the next failed item
                # Yield bypassed items as we go
                next_failed = None
                for item in it:
                    if predicate(item):
                        # Bypassed item: yield to caller
                        yield item
                    else:
                        next_failed = item
                        break

                if next_failed is None:
                    # No more items at all; tell handler we're done
                    msg_type, payload = handler_gl.switch(("end", None))
                    continue

            # Provide the failed item to the handler's stream
            msg_type, payload = handler_gl.switch(("item", next_failed))

        elif msg_type == "output":
            # Handler produced a value
            yield payload
            # Continue conversation
            msg_type, payload = handler_gl.switch()

        elif msg_type == "handler_done":
            # Handler finished; all items must be consumed at this point
            return

        else:
            raise RuntimeError(f"Unexpected message from handler: {msg_type}")
