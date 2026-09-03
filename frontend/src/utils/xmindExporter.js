const encoder = new TextEncoder();

const crcTable = (() => {
  const table = new Uint32Array(256);
  for (let i = 0; i < 256; i += 1) {
    let c = i;
    for (let j = 0; j < 8; j += 1) {
      c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    }
    table[i] = c >>> 0;
  }
  return table;
})();

const crc32 = (bytes) => {
  let crc = 0xffffffff;
  for (let i = 0; i < bytes.length; i += 1) {
    crc = crcTable[(crc ^ bytes[i]) & 0xff] ^ (crc >>> 8);
  }
  return (crc ^ 0xffffffff) >>> 0;
};

const writeUint16 = (view, offset, value) => {
  view.setUint16(offset, value, true);
};

const writeUint32 = (view, offset, value) => {
  view.setUint32(offset, value >>> 0, true);
};

const dosDateTime = (date = new Date()) => {
  const time =
    ((date.getHours() & 0x1f) << 11) |
    ((date.getMinutes() & 0x3f) << 5) |
    (Math.floor(date.getSeconds() / 2) & 0x1f);
  const dosDate =
    (((date.getFullYear() - 1980) & 0x7f) << 9) |
    (((date.getMonth() + 1) & 0x0f) << 5) |
    (date.getDate() & 0x1f);
  return { time, date: dosDate };
};

const concatUint8Arrays = (parts) => {
  const total = parts.reduce((sum, part) => sum + part.length, 0);
  const merged = new Uint8Array(total);
  let offset = 0;
  parts.forEach((part) => {
    merged.set(part, offset);
    offset += part.length;
  });
  return merged;
};

const createZip = (files) => {
  const localParts = [];
  const centralParts = [];
  const now = dosDateTime();
  let offset = 0;

  files.forEach((file) => {
    const nameBytes = encoder.encode(file.name);
    const dataBytes =
      typeof file.data === "string" ? encoder.encode(file.data) : file.data;
    const checksum = crc32(dataBytes);

    const localHeader = new Uint8Array(30 + nameBytes.length);
    const localView = new DataView(localHeader.buffer);
    writeUint32(localView, 0, 0x04034b50);
    writeUint16(localView, 4, 20);
    writeUint16(localView, 6, 0x0800);
    writeUint16(localView, 8, 0);
    writeUint16(localView, 10, now.time);
    writeUint16(localView, 12, now.date);
    writeUint32(localView, 14, checksum);
    writeUint32(localView, 18, dataBytes.length);
    writeUint32(localView, 22, dataBytes.length);
    writeUint16(localView, 26, nameBytes.length);
    writeUint16(localView, 28, 0);
    localHeader.set(nameBytes, 30);

    localParts.push(localHeader, dataBytes);

    const centralHeader = new Uint8Array(46 + nameBytes.length);
    const centralView = new DataView(centralHeader.buffer);
    writeUint32(centralView, 0, 0x02014b50);
    writeUint16(centralView, 4, 20);
    writeUint16(centralView, 6, 20);
    writeUint16(centralView, 8, 0x0800);
    writeUint16(centralView, 10, 0);
    writeUint16(centralView, 12, now.time);
    writeUint16(centralView, 14, now.date);
    writeUint32(centralView, 16, checksum);
    writeUint32(centralView, 20, dataBytes.length);
    writeUint32(centralView, 24, dataBytes.length);
    writeUint16(centralView, 28, nameBytes.length);
    writeUint16(centralView, 30, 0);
    writeUint16(centralView, 32, 0);
    writeUint16(centralView, 34, 0);
    writeUint16(centralView, 36, 0);
    writeUint32(centralView, 38, 0);
    writeUint32(centralView, 42, offset);
    centralHeader.set(nameBytes, 46);

    centralParts.push(centralHeader);
    offset += localHeader.length + dataBytes.length;
  });

  const centralDirectory = concatUint8Arrays(centralParts);
  const endRecord = new Uint8Array(22);
  const endView = new DataView(endRecord.buffer);
  writeUint32(endView, 0, 0x06054b50);
  writeUint16(endView, 4, 0);
  writeUint16(endView, 6, 0);
  writeUint16(endView, 8, files.length);
  writeUint16(endView, 10, files.length);
  writeUint32(endView, 12, centralDirectory.length);
  writeUint32(endView, 16, offset);
  writeUint16(endView, 20, 0);

  return new Blob([...localParts, centralDirectory, endRecord], {
    type: "application/vnd.xmind.workbook",
  });
};

const cleanText = (value) =>
  String(value ?? "")
    .replace(/<br\s*\/?>/gi, "\n")
    .replace(/\*\*([^*]+)\*\*/g, "$1")
    .replace(/\r\n/g, "\n")
    .trim();

const splitLines = (value) =>
  cleanText(value)
    .split("\n")
    .map((line) => line.replace(/^\s*(\d+[.)、]?|[-*])\s*/, "").trim())
    .filter(Boolean);

const topicId = (() => {
  let index = 0;
  return (prefix = "topic") => {
    index += 1;
    return `${prefix}-${Date.now().toString(36)}-${index.toString(36)}`;
  };
})();

const makeTopic = (title, children = []) => ({
  id: topicId(),
  title: cleanText(title) || "未命名",
  children: children.length ? { attached: children } : undefined,
});

const caseToTopic = (testCase, index, labels) => {
  const caseId = cleanText(
    testCase.caseId ||
      testCase.number ||
      `TC${String(index + 1).padStart(3, "0")}`,
  );
  const scenario = cleanText(
    testCase.scenario || testCase.title || labels.untitledCase,
  );
  const priority = cleanText(testCase.priority || "P2");
  const children = [];

  const precondition = splitLines(testCase.precondition);
  if (precondition.length) {
    children.push(
      makeTopic(
        labels.precondition,
        precondition.map((line) => makeTopic(line)),
      ),
    );
  }

  const steps = splitLines(testCase.steps);
  if (steps.length) {
    children.push(
      makeTopic(
        labels.steps,
        steps.map((line, lineIndex) => makeTopic(`${lineIndex + 1}. ${line}`)),
      ),
    );
  }

  const expected = splitLines(testCase.expected);
  if (expected.length) {
    children.push(
      makeTopic(
        labels.expected,
        expected.map((line) => makeTopic(line)),
      ),
    );
  }

  children.push(makeTopic(`${labels.priority}: ${priority}`));
  return makeTopic(`${caseId} ${scenario}`, children);
};

export const worksheetRowsToTestCases = (rows) => {
  if (!Array.isArray(rows) || rows.length === 0) return [];
  const header = rows[0].map((item) => cleanText(item).toLowerCase());

  const findIndex = (matchers, fallback) => {
    const index = header.findIndex((cell) =>
      matchers.some((matcher) => cell.includes(matcher)),
    );
    return index >= 0 ? index : fallback;
  };

  const indexMap = {
    caseId: findIndex(["用例", "case", "编号", "id"], 0),
    scenario: findIndex(["场景", "目标", "标题", "scenario"], 1),
    precondition: findIndex(["前置", "前提", "precondition"], 2),
    steps: findIndex(["步骤", "操作", "steps"], 3),
    expected: findIndex(["预期", "结果", "expected"], 4),
    priority: findIndex(["优先级", "priority"], 5),
  };

  return rows
    .slice(1)
    .map((row, index) => ({
      caseId: cleanText(
        row[indexMap.caseId] || `TC${String(index + 1).padStart(3, "0")}`,
      ),
      scenario: cleanText(row[indexMap.scenario]),
      precondition: cleanText(row[indexMap.precondition]),
      steps: cleanText(row[indexMap.steps]),
      expected: cleanText(row[indexMap.expected]),
      priority: cleanText(row[indexMap.priority] || "P2"),
    }))
    .filter(
      (item) => item.caseId || item.scenario || item.steps || item.expected,
    );
};

export const downloadXmind = (testCases, options = {}) => {
  const labels = {
    rootTitle: options.rootTitle || "AI生成测试用例",
    precondition: options.preconditionLabel || "前置条件",
    steps: options.stepsLabel || "操作步骤",
    expected: options.expectedLabel || "预期结果",
    priority: options.priorityLabel || "优先级",
    untitledCase: options.untitledCaseLabel || "未命名用例",
  };

  const normalizedCases = Array.isArray(testCases) ? testCases : [];
  const rootTopic = makeTopic(
    labels.rootTitle,
    normalizedCases.map((testCase, index) =>
      caseToTopic(testCase, index, labels),
    ),
  );

  const content = [
    {
      id: topicId("sheet"),
      class: "sheet",
      title: labels.rootTitle,
      rootTopic,
    },
  ];

  const metadata = {
    creator: {
      name: "QAFlow",
      version: "1.0.1",
    },
    activeSheetId: content[0].id,
  };

  const manifest = {
    "file-entries": {
      "content.json": {},
      "metadata.json": {},
      "manifest.json": {},
    },
  };

  const blob = createZip([
    { name: "content.json", data: JSON.stringify(content, null, 2) },
    { name: "metadata.json", data: JSON.stringify(metadata, null, 2) },
    { name: "manifest.json", data: JSON.stringify(manifest, null, 2) },
  ]);

  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = options.fileName || "AI生成测试用例.xmind";
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(link.href);
};
