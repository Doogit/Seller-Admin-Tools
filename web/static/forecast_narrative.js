// Dirty-guarded Regenerate (inventory §C / plan Q3): htmx has no native
// "warn on unsaved edits", so gate the htmx:confirm event ourselves. Fire the
// browser confirm ONLY when a draft textarea differs from its last generated
// text; otherwise regenerate silently. Offline, no dependencies beyond htmx.
document.addEventListener('htmx:confirm', function (e) {
  var el = e.detail.elt;
  if (!el || !el.hasAttribute('data-confirm-dirty')) return; // let others proceed
  e.preventDefault();
  var dirty = Array.prototype.some.call(
    document.querySelectorAll('#draft-form textarea'),
    function (t) { return t.value !== t.getAttribute('data-generated'); }
  );
  if (!dirty || window.confirm('Discard your edits and regenerate from current data?')) {
    e.detail.issueRequest(true); // true = skip htmx's own confirm
  }
});
