const Api = {
  async getProducts() {
    const res = await fetch(`${window.API_URL}/products`);
    if (!res.ok) throw new Error("Nem sikerült betölteni a termékeket.");
    return res.json();
  },

  async requestUploadUrl(file) {
    const res = await fetch(`${window.API_URL}/uploads`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      // A méret is átmegy: a backend belefoglalja az aláírásba, így a
      // presigned URL-lel pontosan ekkora fájl tölthető fel, se több.
      body: JSON.stringify({ fileName: file.name, contentType: file.type, fileSize: file.size }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.error || "A fotó feltöltése nem sikerült.");
    }
    return res.json(); // { uploadUrl, key }
  },

  async uploadPhoto(file) {
    const { uploadUrl, key } = await this.requestUploadUrl(file);
    const res = await fetch(uploadUrl, {
      method: "PUT",
      headers: { "Content-Type": file.type },
      body: file,
    });
    if (!res.ok) throw new Error("A fotó feltöltése nem sikerült.");
    return key;
  },

  async getFoxpostLockers(params = {}) {
    const qs = new URLSearchParams(params).toString();
    const res = await fetch(`${window.API_URL}/foxpost-lockers${qs ? "?" + qs : ""}`);
    if (!res.ok) throw new Error("Nem sikerült betölteni a csomagautomatákat.");
    return res.json(); // { lockers: [...] }
  },

  async createOrder(payload) {
    const res = await fetch(`${window.API_URL}/orders`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "A rendelés leadása nem sikerült.");
    return data; // { orderId, gatewayUrl }
  },

  async sendContactMessage(payload) {
    const res = await fetch(`${window.API_URL}/contact`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Az üzenet küldése nem sikerült.");
    return data;
  },

  async getOrderStatus(orderId) {
    const res = await fetch(`${window.API_URL}/orders/${orderId}`);
    if (!res.ok) throw new Error("A rendelés nem található.");
    return res.json();
  },
};
