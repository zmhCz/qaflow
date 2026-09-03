export const semanticPageOptions = [
  "登录页",
  "验证码登录页",
  "创建社区页",
  "社区详情页",
  "关注列表页",
  "个人中心页",
  "设置页",
  "公共弹窗",
  "公共顶部栏",
  "公共Toast",
];

export const semanticRoleOptions = [
  "按钮",
  "输入框",
  "文本",
  "列表项",
  "图片",
  "开关",
  "勾选框",
  "弹窗",
  "Tab",
  "Toast",
  "容器",
];

export const semanticObjectOptions = [
  "手机号",
  "验证码",
  "登录",
  "退出登录",
  "取消",
  "确认",
  "返回",
  "社区名称",
  "社区介绍",
  "创建社区",
  "关注社区",
  "关注列表",
  "社区头像",
  "个人头像",
  "昵称",
  "搜索",
  "设置",
];

export const semanticPurposeOptions = [
  "点击",
  "输入",
  "展示",
  "断言",
  "选择",
  "返回",
  "确认",
  "取消",
];

const cleanNamePart = (value) =>
  String(value || "")
    .trim()
    .replace(/[.\s]+/g, "");

export const buildSemanticElementName = ({ page, object, role }) => {
  const parts = [
    cleanNamePart(page),
    cleanNamePart(object),
    cleanNamePart(role),
  ].filter(Boolean);
  return parts.join(".");
};

export const querySemanticObjectSuggestions = (queryString, callback) => {
  const keyword = String(queryString || "").trim();
  const candidates = semanticObjectOptions
    .filter((item) => !keyword || item.includes(keyword))
    .map((item) => ({ value: item }));

  callback(candidates);
};

export const buildSemanticTags = (tags = []) => {
  const next = Array.isArray(tags) ? [...tags] : [];
  for (const tag of ["semantic_v2", "语义元素"]) {
    if (!next.includes(tag)) next.push(tag);
  }
  return next;
};

export const pickSemanticFields = (config = {}) => ({
  semantic_page: config.semantic_page || "",
  semantic_object: config.semantic_object || "",
  semantic_role: config.semantic_role || "",
  interaction_role: config.semantic_role || config.interaction_role || "",
  semantic_purpose: config.semantic_purpose || "",
});
