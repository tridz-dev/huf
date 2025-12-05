// Find the scrollable container (window, document body, or a parent element)
export function findScrollableContainer(element: HTMLElement): HTMLElement | Window {
    // Check if window/document is scrollable
    if (document.documentElement.scrollHeight > window.innerHeight) {
      return window;
    }
    if (document.body.scrollHeight > window.innerHeight) {
      return document.body;
    }

    // Find scrollable parent element
    let parentElement: HTMLElement | null = element;
    while (parentElement) {
      const style = window.getComputedStyle(parentElement);
      if (
        (style.overflowY === 'auto' || style.overflowY === 'scroll' || 
         style.overflow === 'auto' || style.overflow === 'scroll') &&
        parentElement.scrollHeight > parentElement.clientHeight
      ) {
        return parentElement;
      }
      parentElement = parentElement.parentElement;
    }

    // Fallback to window
    return window;
};