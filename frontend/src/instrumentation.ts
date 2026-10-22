export function register() {
  if (process.env.NEXT_RUNTIME === "nodejs") {
    console.info("[runtime]", JSON.stringify({ node: process.version }));
  }
}
