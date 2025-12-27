from greenlet import greenlet

def bypass(iterable, should_bypass_handler, handler):
    """
    Interleaves items from an iterable with outputs from a handler, based on a predicate.
    
    Parameters:
        iterable:  input iterable
        should_bypass_handler: function(item) -> bool
        handler:   function(iterator_of_processable_items) -> iterator

    Behavior:
      - Items with should_bypass_handler(item) == True are yielded directly (bypassed).
      - Items with should_bypass_handler(item) == False are sent to `handler`, which is
        called exactly once with a single iterator over the processable items.
      - The outputs of `handler` are interleaved with bypassed items in the
        order implied by the original stream.
    
    Flow:
      The function uses cooperative multitasking (greenlets) to coordinate between the
      main iteration loop and the handler. The overall flow works as follows:
      
      1. The handler runs in its own greenlet and requests processable items on demand
         via the `processable()` iterator.
      
      2. The main loop scans the input iterable, yielding bypassed items immediately
         as they are encountered.
      
      3. When a processable item is found, the main loop pauses scanning and sends the
         item to the handler. The handler processes it and may produce zero or more
         outputs, each of which is yielded immediately.
      
      4. After the handler finishes with an item (or produces outputs), control returns
         to the main loop, which resumes scanning for the next item.
      
      5. This cooperative back-and-forth continues until all items are consumed and
         the handler finishes processing.
      
      This design ensures that outputs from the handler are interleaved with bypassed
      items in the order they appear in the original stream, while maintaining lazy
      evaluation and avoiding the need to buffer the entire stream.
      
    Example:
      >>> data = [2, 3, 4, 5]
      >>> bypass(data, lambda x: x % 2 == 0, lambda items: (10*x for x in items))
      [2, 30, 4, 50]  # Even numbers bypassed, odd numbers processed by handler
    """
    it = iter(iterable)
    outer_gl = greenlet.getcurrent()
    
    # Iterator that provides processable items to handler on demand
    def processable():
        while True:
            # Request next processable item from outer
            msg, value = outer_gl.switch(("need_item", None))
            if msg == "item":
                yield value
            elif msg == "end":
                break
            else:
                raise RuntimeError(f"Unexpected message: {msg}")
    
    # Handler runs in its own greenlet
    def run_handler():
        for output in handler(processable()):
            outer_gl.switch(("output", output))
        outer_gl.switch(("done", None))
    
    handler_gl = greenlet(run_handler)
    msg, value = handler_gl.switch()  # Start handler; it will request first item
    
    # Main loop: scan items and coordinate with handler
    while True:
        if msg == "need_item":
            # Handler needs next processable item
            # Scan until we find one, yielding bypassed items
            found = False
            for item in it:
                if should_bypass_handler(item):
                    yield item
                else:
                    # Found processable item
                    msg, value = handler_gl.switch(("item", item))
                    found = True
                    break
            
            if not found:
                # No more items
                msg, value = handler_gl.switch(("end", None))
                
        elif msg == "output":
            # Handler produced output
            yield value
            msg, value = handler_gl.switch()
            
        elif msg == "done":
            # Handler finished
            break
            
        else:
            raise RuntimeError(f"Unexpected message: {msg}")
