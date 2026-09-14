/**
 * Local preview store for the customer's uploaded photo.
 *
 * The photo itself goes straight to S3 through a presigned PUT, and the
 * cart cookie only keeps the returned S3 key — the bucket is not public,
 * so there is no URL the browser could read the image back from. To still
 * show the customer what they uploaded, we keep a small downscaled copy in
 * localStorage under that same key. The cookie stays tiny; localStorage
 * holds the pixels, and nothing extra is sent to the server.
 *
 * Every read is defensive: private mode, a full quota or a cleared storage
 * must degrade to "no preview", never to a broken cart.
 */

const PHOTO_PREFIX = "litho_photo_";
const PREVIEW_MAX_PX = 900;   // long edge — enough for the lightbox
const PREVIEW_QUALITY = 0.82;

const PhotoStore = {
  /** Downscale a File to a JPEG data URL suitable for previewing. */
  async makePreview(file) {
    const bitmap = await loadBitmap(file);
    const scale = Math.min(1, PREVIEW_MAX_PX / Math.max(bitmap.width, bitmap.height));
    const w = Math.max(1, Math.round(bitmap.width * scale));
    const h = Math.max(1, Math.round(bitmap.height * scale));

    const canvas = document.createElement("canvas");
    canvas.width = w;
    canvas.height = h;
    const ctx = canvas.getContext("2d");
    ctx.drawImage(bitmap, 0, 0, w, h);
    if (bitmap.close) bitmap.close();

    return canvas.toDataURL("image/jpeg", PREVIEW_QUALITY);
  },

  save(key, dataUrl) {
    if (!key || !dataUrl) return false;
    try {
      localStorage.setItem(PHOTO_PREFIX + key, dataUrl);
      return true;
    } catch (e) {
      // Quota full or storage blocked — the order still works without a preview.
      return false;
    }
  },

  get(key) {
    if (!key) return null;
    try {
      return localStorage.getItem(PHOTO_PREFIX + key);
    } catch (e) {
      return null;
    }
  },

  remove(key) {
    if (!key) return;
    try {
      localStorage.removeItem(PHOTO_PREFIX + key);
    } catch (e) {
      /* nothing to clean up */
    }
  },

  /** Drop previews whose cart item is gone, so storage cannot grow forever. */
  prune(keepKeys) {
    const keep = new Set(keepKeys || []);
    try {
      for (let i = localStorage.length - 1; i >= 0; i--) {
        const storageKey = localStorage.key(i);
        if (!storageKey || !storageKey.startsWith(PHOTO_PREFIX)) continue;
        if (!keep.has(storageKey.slice(PHOTO_PREFIX.length))) {
          localStorage.removeItem(storageKey);
        }
      }
    } catch (e) {
      /* storage unavailable */
    }
  },
};

/**
 * Decode the file. createImageBitmap applies the EXIF orientation for us;
 * drawing a plain <img> to a canvas would not, so phone photos taken in
 * portrait would come out sideways in the preview.
 */
async function loadBitmap(file) {
  if (window.createImageBitmap) {
    try {
      return await createImageBitmap(file, { imageOrientation: "from-image" });
    } catch (e) {
      /* older Safari: fall through to the <img> path */
    }
  }
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file);
    const img = new Image();
    img.onload = () => {
      URL.revokeObjectURL(url);
      resolve(img);
    };
    img.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new Error("A képet nem sikerült beolvasni."));
    };
    img.src = url;
  });
}
