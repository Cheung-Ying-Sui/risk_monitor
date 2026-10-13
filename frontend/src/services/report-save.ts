type SavePicker = (options: { suggestedName: string; types: Array<{ description: string; accept: Record<string, string[]> }> }) => Promise<FileSystemFileHandle>;

/** Never bypass a cancelled picker; platform write failures use normal downloads. */
export async function saveReport(blob: Blob, filename: string, picker: SavePicker | undefined,
  download: (blob: Blob, filename: string) => void): Promise<"saved" | "download" | "fallback" | "cancelled"> {
  if (!blob.size) throw new Error("报告为空，请重新生成。");
  if (!picker) { download(blob, filename); return "download"; }
  let handle: FileSystemFileHandle;
  try {
    handle = await picker({ suggestedName: filename, types: [{ description: "Word 文档",
      accept: { "application/vnd.openxmlformats-officedocument.wordprocessingml.document": [".docx"] } }] });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") return "cancelled";
    download(blob, filename);
    return "fallback";
  }
  try {
    const writable = await handle.createWritable();
    try {
      await writable.write(blob);
      await writable.close();
    } catch (error) {
      await writable.abort().catch(() => undefined);
      throw error;
    }
    if ((await handle.getFile()).size !== blob.size) throw new Error("文件保存不完整");
    return "saved";
  } catch {
    download(blob, filename);
    return "fallback";
  }
}

export function browserDownload(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.append(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
}
