document.addEventListener('DOMContentLoaded', function() {
    const pacman = document.createElement('div');
    pacman.style.position = 'absolute';
    pacman.style.width = '50px';
    pacman.style.height = '50px';
    pacman.style.backgroundColor = 'yellow';
    pacman.style.borderRadius = '50%';
    pacman.style.left = '50%';
    pacman.style.top = '50%';
    pacman.style.transform = 'translate(-50%, -50%)';
    document.body.appendChild(pacman);
    let x = window.innerWidth / 2;
    let y = window.innerHeight / 2;
    document.addEventListener('keydown', function(e) {
        const step = 10;
        switch (e.key) {
            case 'ArrowUp':
                y -= step;
                break;
            case 'ArrowDown':
                y += step;
                break;
            case 'ArrowLeft':
                x -= step;
                break;
            case 'ArrowRight':
                x += step;
                break;
        }
        pacman.style.left = x + 'px';
        pacman.style.top = y + 'px';
    });
});