# Canvas Editing Instructions

You are editing a Canvas artifact. This is an HTML/CSS/JS page designed to be a visual interface.

## Your Capabilities

- Read files: `read_canvas_file(path)`
- Write files: `write_canvas_files({html, css, js, py, md})`
- Validate: `validate_canvas()`

## Guidelines

1. Always read `agents.md` first to understand context
2. Read existing files before making changes
3. Maintain semantic HTML structure
4. Keep CSS organized and readable
5. Use vanilla JavaScript (no frameworks unless specified)
6. Test with `validate_canvas()` before major changes
7. Write clean, commented code

## File Structure

- `index.html` - Main HTML structure
- `index.css` - Styling
- `index.js` - Client-side JavaScript
- `index.py` - Server-side Python context
- `agents.md` - This file (editing instructions)

## Best Practices

- Use `#canvas-root` as the main container
- Keep responsive design in mind
- Follow accessibility guidelines
- Comment complex logic
- Maintain consistent indentation