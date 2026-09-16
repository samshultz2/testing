// Resize + re-encode a photo client-side before it goes into a form's JSON/
// form-data payload. A modern phone photo is routinely 8-20MB, which blows
// past both the server's request-size caps and what a passport/ID photo
// needs — instead of rejecting those outright, always downscale to a
// generous resolution and re-encode as a high-quality JPEG first. 1400px on
// the long side is far more detail than any of this app's passport-style
// crops need, so there's no visible quality loss; the result is typically a
// few hundred KB regardless of how large the original file was.
export function compressPhoto(file, { maxDim = 1400, quality = 0.9 } = {}) {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file);
    const img = new Image();
    img.onload = () => {
      URL.revokeObjectURL(url);
      const scale = Math.min(1, maxDim / Math.max(img.width, img.height));
      const w = Math.max(1, Math.round(img.width * scale));
      const h = Math.max(1, Math.round(img.height * scale));
      const canvas = document.createElement('canvas');
      canvas.width = w; canvas.height = h;
      canvas.getContext('2d').drawImage(img, 0, 0, w, h);
      resolve(canvas.toDataURL('image/jpeg', quality));
    };
    img.onerror = () => { URL.revokeObjectURL(url); reject(new Error('load-failed')); };
    img.src = url;
  });
}
