// Copy text without ever throwing. The async Clipboard API can refuse — on
// Android Chrome it rejects with "Document is not focused" when a dialog or
// the keyboard has focus, and it is missing on plain-HTTP pages — so fall back
// to the old hidden-textarea + execCommand('copy'), which works inside the
// same tap. Resolves true when the text reached the clipboard, else false.
function legacyCopy(text) {
  try {
    const ta = document.createElement('textarea');
    ta.value = text;
    ta.setAttribute('readonly', '');
    ta.style.cssText = 'position:fixed;top:0;left:0;opacity:0;pointer-events:none';
    document.body.appendChild(ta);
    const prev = document.activeElement;
    ta.focus();
    ta.select();
    ta.setSelectionRange(0, text.length);
    const ok = document.execCommand('copy');
    document.body.removeChild(ta);
    if (prev && prev.focus) { try { prev.focus({ preventScroll: true }); } catch (e) { /* ignore */ } }
    return ok;
  } catch (e) {
    return false;
  }
}

export async function copyText(value) {
  const text = String(value == null ? '' : value);
  try {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch (e) { /* refused — try the fallback below */ }
  return legacyCopy(text);
}
