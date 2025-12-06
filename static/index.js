$(function() {
    var observer = new MutationObserver(function(mutations) {
        mutations.forEach(function(mutation) {
            mutation.addedNodes.forEach(function(node) {
                if (node.classList && node.classList.contains('flash-message')) {
                    console.log('Flash message added:', node);
                    setTimeout(function() {
                        console.log('Removing flash message:', node);
                        node.remove();
                    }, 5000);
                }
            });
        });
    });

    var parent = document.getElementById('flashed-messages');
    if (parent) {
        observer.observe(parent, { childList: true });
    }
});

$(function() {
    window.setTimeout(function() {
        Array.from(document.getElementsByClassName('flash-message')).forEach(e => e.remove());
    }, 5000);
})