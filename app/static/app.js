const fixedInput = document.getElementById("fixed-input");
const attachmentsInput = document.getElementById("attachments-input");
const headerPreview = document.getElementById("header-preview");
const attachmentsPreview = document.getElementById("attachments-preview");
const results = document.getElementById("results");
const statusEl = document.getElementById("status");
const btnSaveHeader = document.getElementById("btn-save-header");
const btnMerge = document.getElementById("btn-merge");

let headerDirty = false;
let headerSaved = false;
let headerObjectUrl = null;
let attachmentUrls = [];
let attachmentFiles = [];
let dragSrcIndex = null;

function setStatus(message, tone = "") {
  statusEl.textContent = message;
  statusEl.className = `status ${tone}`;
}

function clearResults() {
  results.innerHTML = "";
}

function cleanupUrls() {
  if (headerObjectUrl) {
    URL.revokeObjectURL(headerObjectUrl);
  }
  attachmentUrls.forEach((url) => URL.revokeObjectURL(url));
  attachmentUrls = [];
}

function setFilesOnInput(input, files) {
  const dt = new DataTransfer();
  Array.from(files).forEach((file) => dt.items.add(file));
  input.files = dt.files;
}

function isPdfFile(file) {
  if (!file) return false;
  const nameOk = file.name && file.name.toLowerCase().endsWith(".pdf");
  const typeOk = file.type === "application/pdf";
  return nameOk || typeOk;
}

function renderHeaderPreview(file) {
  if (headerObjectUrl) {
    URL.revokeObjectURL(headerObjectUrl);
  }
  const overlay = headerPreview.querySelector(".drop-overlay");
  headerPreview.innerHTML = "";
  headerObjectUrl = URL.createObjectURL(file);
  headerPreview.innerHTML = `<embed src="${headerObjectUrl}" type="application/pdf" />`;
  if (overlay) {
    headerPreview.appendChild(overlay);
  }
}

function renderAttachmentsPreview(files) {
  const overlay = attachmentsPreview.querySelector(".drop-overlay");
  attachmentsPreview.innerHTML = "";
  attachmentUrls.forEach((url) => URL.revokeObjectURL(url));
  attachmentUrls = [];
  attachmentFiles = Array.from(files);

  if (overlay) attachmentsPreview.appendChild(overlay);

  if (!attachmentFiles.length) {
    const ph = document.createElement("div");
    ph.className = "placeholder";
    ph.textContent = "Prévia dos anexos";
    attachmentsPreview.appendChild(ph);
    return;
  }

  attachmentFiles.forEach((file, index) => {
    const tile = document.createElement("div");
    tile.className = "preview-tile";
    tile.draggable = true;
    const url = URL.createObjectURL(file);
    attachmentUrls.push(url);
    tile.innerHTML = `
      <div class="drag-handle">&#8942;&#8942;</div>
      <embed src="${url}" type="application/pdf" />
      <div class="tile-name">${file.name}</div>
    `;

    tile.addEventListener("dragstart", (e) => {
      dragSrcIndex = index;
      tile.classList.add("dragging");
      e.dataTransfer.effectAllowed = "move";
    });

    tile.addEventListener("dragend", () => {
      tile.classList.remove("dragging");
      attachmentsPreview.querySelectorAll(".preview-tile").forEach((t) => t.classList.remove("drag-over"));
    });

    tile.addEventListener("dragover", (e) => {
      e.preventDefault();
      e.stopPropagation();
      e.dataTransfer.dropEffect = "move";
      attachmentsPreview.querySelectorAll(".preview-tile").forEach((t) => t.classList.remove("drag-over"));
      tile.classList.add("drag-over");
    });

    tile.addEventListener("drop", (e) => {
      e.preventDefault();
      e.stopPropagation();
      tile.classList.remove("drag-over");
      if (dragSrcIndex === null || dragSrcIndex === index) return;
      const moved = attachmentFiles.splice(dragSrcIndex, 1)[0];
      attachmentFiles.splice(index, 0, moved);
      dragSrcIndex = null;
      setFilesOnInput(attachmentsInput, attachmentFiles);
      renderAttachmentsPreview(attachmentFiles);
    });

    attachmentsPreview.appendChild(tile);
  });
}

function clearAttachmentsSelection() {
  attachmentsInput.value = "";
  renderAttachmentsPreview([]);
}

async function checkFixed() {
  const resp = await fetch("/api/fixed");
  const data = await resp.json();
  headerSaved = data.has_fixed;
  if (headerSaved) {
    setStatus("Cabeçalho já definido nesta sessão.");
  }
}

async function uploadHeader() {
  const file = fixedInput.files[0];
  if (!file) {
    setStatus("Selecione um PDF de cabeçalho.", "warn");
    return false;
  }

  const formData = new FormData();
  formData.append("fixed", file);

  setStatus("Salvando cabeçalho...");
  btnSaveHeader.disabled = true;

  const resp = await fetch("/api/fixed", { method: "POST", body: formData });
  const data = await resp.json();

  btnSaveHeader.disabled = false;

  if (!resp.ok) {
    setStatus(data.error || "Falha ao salvar cabeçalho.", "warn");
    return false;
  }

  headerDirty = false;
  headerSaved = true;
  setStatus("Cabeçalho salvo. Pronto para gerar PDFs.");
  return true;
}

async function mergePdfs() {
  const files = attachmentsInput.files;
  if (!files.length) {
    setStatus("Selecione pelo menos um PDF anexo.", "warn");
    return;
  }

  if (!headerSaved || headerDirty) {
    const ok = await uploadHeader();
    if (!ok) return;
  }

  const formData = new FormData();
  Array.from(files).forEach((file) => formData.append("attachments", file));

  btnMerge.disabled = true;
  setStatus("Gerando PDFs...");

  const resp = await fetch("/api/merge", { method: "POST", body: formData });
  const data = await resp.json();

  btnMerge.disabled = false;

  if (!resp.ok) {
    setStatus(data.error || "Falha ao gerar PDFs.", "warn");
    if (data.details) {
      setStatus(`${data.error}: ${data.details.join("; ")}`, "warn");
    }
    return;
  }

  clearResults();

  if (data.files.length > 1) {
    const zipBtn = document.createElement("a");
    zipBtn.className = "btn primary zip-btn";
    zipBtn.href = `/api/zip/${data.job_id}`;
    zipBtn.textContent = `Baixar todos em ZIP (${data.files.length} arquivos)`;
    results.appendChild(zipBtn);
  }

  data.files.forEach((item) => {
    const row = document.createElement("div");
    row.className = "result-item";
    row.innerHTML = `
      <div class="result-preview">
        <embed src="${item.preview_url || item.url}" type="application/pdf" />
      </div>
      <div class="result-name">${item.name}</div>
      <a href="${item.url}">Download</a>
    `;
    results.appendChild(row);
  });

  if (data.errors && data.errors.length) {
    setStatus(`Gerado com avisos: ${data.errors.join("; ")}`, "warn");
  } else {
    setStatus("PDFs gerados com sucesso.");
  }

  clearAttachmentsSelection();
}

fixedInput.addEventListener("change", (event) => {
  const files = Array.from(event.target.files || []);
  if (!files.length) return;
  const pdfs = files.filter(isPdfFile);
  if (!pdfs.length) {
    setStatus("Selecione um PDF válido para o cabeçalho.", "warn");
    fixedInput.value = "";
    return;
  }
  if (pdfs.length > 1) {
    setStatus("Usando apenas o primeiro PDF do cabeçalho.", "warn");
  }
  if (pdfs.length < files.length) {
    setFilesOnInput(fixedInput, [pdfs[0]]);
  }
  const file = pdfs[0];
  headerDirty = true;
  renderHeaderPreview(file);
  setStatus("Cabeçalho selecionado. Clique em 'Salvar cabeçalho'.");
});

attachmentsInput.addEventListener("change", (event) => {
  const files = Array.from(event.target.files || []);
  if (!files.length) {
    renderAttachmentsPreview([]);
    return;
  }
  const pdfs = files.filter(isPdfFile);
  if (!pdfs.length) {
    setStatus("Selecione apenas PDFs nos anexos.", "warn");
    attachmentsInput.value = "";
    renderAttachmentsPreview([]);
    return;
  }
  if (pdfs.length < files.length) {
    setStatus("Alguns arquivos não eram PDF e foram ignorados.", "warn");
    setFilesOnInput(attachmentsInput, pdfs);
  } else {
    setStatus(`${pdfs.length} PDF(s) selecionado(s).`);
  }
  renderAttachmentsPreview(pdfs);
});

function bindDropzone(element, kind) {
  element.addEventListener("dragenter", (event) => {
    event.preventDefault();
    element.classList.add("dragover");
  });

  element.addEventListener("dragover", (event) => {
    event.preventDefault();
    element.classList.add("dragover");
  });

  element.addEventListener("dragleave", () => {
    element.classList.remove("dragover");
  });

  element.addEventListener("drop", (event) => {
    event.preventDefault();
    element.classList.remove("dragover");
    const files = event.dataTransfer.files;
    if (!files || !files.length) return;
    if (kind === "header") {
      const pdfs = Array.from(files).filter(isPdfFile);
      if (!pdfs.length) {
        setStatus("Nenhum PDF válido no cabeçalho.", "warn");
        return;
      }
      if (pdfs.length > 1) {
        setStatus("Usando apenas o primeiro PDF do cabeçalho.", "warn");
      }
      setFilesOnInput(fixedInput, [pdfs[0]]);
      headerDirty = true;
      renderHeaderPreview(pdfs[0]);
      setStatus("Cabeçalho selecionado. Clique em 'Salvar cabeçalho'.");
    } else {
      const pdfs = Array.from(files).filter(isPdfFile);
      if (!pdfs.length) {
        setStatus("Nenhum PDF válido nos anexos.", "warn");
        return;
      }
      if (pdfs.length < files.length) {
        setStatus("Alguns arquivos não eram PDF e foram ignorados.", "warn");
      }
      setFilesOnInput(attachmentsInput, pdfs);
      renderAttachmentsPreview(pdfs);
      setStatus(`${pdfs.length} PDF(s) selecionado(s).`);
    }
  });
}

bindDropzone(headerPreview, "header");
bindDropzone(attachmentsPreview, "attachments");

btnSaveHeader.addEventListener("click", () => {
  uploadHeader();
});

btnMerge.addEventListener("click", () => {
  mergePdfs();
});

window.addEventListener("beforeunload", cleanupUrls);
checkFixed();
