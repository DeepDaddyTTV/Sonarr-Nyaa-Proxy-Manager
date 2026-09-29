(() => {
  const link = document.querySelector('link[rel="icon"]');
  const shape = new Image();
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = 64;
  const context = canvas.getContext("2d");
  if (!link || !context) return;

  function render() {
    if (!shape.complete || !shape.naturalWidth) return;
    const colors = getComputedStyle(document.documentElement);
    const gradient = context.createLinearGradient(0, 0, 64, 64);
    gradient.addColorStop(0, colors.getPropertyValue("--icon-start").trim());
    gradient.addColorStop(0.48, colors.getPropertyValue("--icon-middle").trim());
    gradient.addColorStop(1, colors.getPropertyValue("--icon-end").trim());
    context.clearRect(0, 0, 64, 64);
    context.globalCompositeOperation = "source-over";
    context.fillStyle = gradient;
    context.fillRect(0, 0, 64, 64);
    // Browser tab icons cannot inherit CSS masks, so apply the same alpha mask here.
    context.globalCompositeOperation = "destination-in";
    context.imageSmoothingQuality = "high";
    context.drawImage(shape, 0, 0, 64, 64);
    link.type = "image/png";
    link.href = canvas.toDataURL("image/png");
  }

  shape.addEventListener("load", render);
  shape.src = "/manager/assets/icons/electronic.png";
  new MutationObserver(render).observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
})();
