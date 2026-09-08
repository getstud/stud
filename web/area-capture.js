// Screen-space rectangles only: no ray casting or part selection.
export function selectionRectangle(start, end, width, height) {
  const clamp = (value, max) => Math.max(0, Math.min(max, value));
  const x1 = clamp(start.x, width), y1 = clamp(start.y, height);
  const x2 = clamp(end.x, width), y2 = clamp(end.y, height);
  return {x: Math.min(x1, x2), y: Math.min(y1, y2), width: Math.abs(x2-x1), height: Math.abs(y2-y1)};
}

export function cropPixels(rectangle, screen, image) {
  const x = Math.floor(rectangle.x * image.width / screen.width);
  const y = Math.floor(rectangle.y * image.height / screen.height);
  const right = Math.min(image.width, Math.ceil((rectangle.x+rectangle.width) * image.width / screen.width));
  const bottom = Math.min(image.height, Math.ceil((rectangle.y+rectangle.height) * image.height / screen.height));
  return {x, y, width: right-x, height: bottom-y};
}

export function snapshotViewer(source, labels) {
  const canvas = document.createElement('canvas');
  const scale = Math.min(1, 2048 / Math.max(source.width, source.height));
  canvas.width = Math.max(1, Math.round(source.width * scale));
  canvas.height = Math.max(1, Math.round(source.height * scale));
  const ctx = canvas.getContext('2d');
  ctx.drawImage(source, 0, 0, canvas.width, canvas.height);
  // Dimension labels are HTML overlays; include them in the captured pixels.
  const bounds = source.getBoundingClientRect();
  ctx.save();ctx.scale(canvas.width / bounds.width, canvas.height / bounds.height);
  if (!labels.hidden) for (const label of labels.children) {
    if (label.hidden) continue;
    const box = label.getBoundingClientRect(), style = getComputedStyle(label);
    const x = box.left-bounds.left, y = box.top-bounds.top;
    ctx.fillStyle = style.backgroundColor;ctx.fillRect(x, y, box.width, box.height);
    ctx.strokeStyle = style.borderColor;ctx.lineWidth = 1;ctx.strokeRect(x+.5, y+.5, box.width-1, box.height-1);
    ctx.fillStyle = style.color;ctx.font = style.font;
    ctx.textBaseline = 'middle';
    ctx.fillText(label.textContent, x+parseFloat(style.paddingLeft)+1, y+box.height/2);
  }
  ctx.restore();return canvas;
}

export function installAreaCapture({viewport, capture, save}) {
  const $ = id => document.getElementById(id);
  const overlay = $('areaoverlay'), marquee = $('areamarquee'), dialog = $('areacomment');
  let frozen = null, start = null, draft = null, saving = false;

  function stopCapture() {
    overlay.hidden = true;start = null;frozen = null;
    overlay.querySelector('canvas')?.remove();marquee.hidden = true;
    $('capturearea').setAttribute('aria-pressed', 'false');
  }
  function cancelDraft() {
    if (saving) return;
    dialog.close();draft = null;$('areatext').value = '';$('areapreview').removeAttribute('src');
  }
  $('capturearea').onclick = () => {
    if (!overlay.hidden) {stopCapture();return;}
    try {
      frozen = capture();
      overlay.prepend(frozen.canvas);overlay.hidden = false;marquee.hidden = true;
      $('capturearea').setAttribute('aria-pressed', 'true');
      $('areacancelcapture').focus();
    } catch (error) { $('commentstatus').textContent = error.message; }
  };
  $('areacancelcapture').onclick = stopCapture;
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && !overlay.hidden) {event.preventDefault();stopCapture();}
  });
  const point = event => {
    const box = overlay.getBoundingClientRect();
    return {x: event.clientX-box.left, y: event.clientY-box.top};
  };
  overlay.addEventListener('pointerdown', event => {
    if (event.button !== 0 || event.target.closest('button')) return;
    event.preventDefault();start = point(event);overlay.setPointerCapture(event.pointerId);
    marquee.hidden = true;
  });
  overlay.addEventListener('pointermove', event => {
    if (!start) return;
    const box = overlay.getBoundingClientRect();
    const rect = selectionRectangle(start, point(event), box.width, box.height);
    Object.assign(marquee.style, {left:`${rect.x}px`,top:`${rect.y}px`,width:`${rect.width}px`,height:`${rect.height}px`});
    marquee.hidden = false;
  });
  overlay.addEventListener('pointercancel', () => {start = null;marquee.hidden = true;});
  overlay.addEventListener('pointerup', event => {
    if (!start || !frozen) return;
    const box = overlay.getBoundingClientRect();
    const rect = selectionRectangle(start, point(event), box.width, box.height);
    start = null;overlay.releasePointerCapture(event.pointerId);
    if (rect.width < 8 || rect.height < 8) {marquee.hidden = true;return;}
    const pixels = cropPixels(rect, box, frozen.canvas);
    const image = document.createElement('canvas');image.width = pixels.width;image.height = pixels.height;
    image.getContext('2d').drawImage(frozen.canvas, pixels.x, pixels.y, pixels.width, pixels.height, 0, 0, pixels.width, pixels.height);
    draft = {action:'add',kind:'area',id:crypto.randomUUID(),revision:frozen.revision,image:image.toDataURL('image/png')};
    stopCapture();$('areapreview').src = draft.image;$('areatext').value = '';$('areastatus').textContent = '';
    dialog.showModal();$('areatext').focus();
  });
  $('areacancel').onclick = cancelDraft;
  dialog.addEventListener('cancel', event => {event.preventDefault();cancelDraft();});
  $('areaform').onsubmit = async event => {
    event.preventDefault();if (!draft || saving) return;
    const text = $('areatext').value.trim();
    if (!text) {$('areastatus').textContent = 'Enter a comment first.';return;}
    saving = true;$('areasave').disabled = true;$('areacancel').disabled = true;$('areatext').disabled = true;
    $('areastatus').textContent = 'Saving screenshot and comment…';
    try {
      await save({...draft,text});
      saving = false;cancelDraft();
      $('review').scrollIntoView({behavior:'smooth',block:'start'});
    } catch (error) {
      $('areastatus').textContent = `Not confirmed saved: ${error.message} Your screenshot and draft are kept; retry to confirm.`;
    } finally {
      saving = false;$('areasave').disabled = false;$('areacancel').disabled = false;$('areatext').disabled = false;
    }
  };
}
