// Local testing (see local-test/README.md): points at local-test/server.py.
// Before deploying to Amplify, replace this with your real API Gateway URL,
// e.g. "https://abc123xyz.execute-api.eu-central-1.amazonaws.com"
window.API_URL = "http://localhost:8787";

// Bumped whenever the CSS/JS changes; the HTML pages carry it as a ?v=
// query on every asset URL so a browser cannot keep serving an old copy.
// Printing it makes "which version am I actually looking at?" a one-glance
// question in the console.
window.ASSET_VERSION = "20260914a";
console.info("Fény·kép build " + window.ASSET_VERSION);
