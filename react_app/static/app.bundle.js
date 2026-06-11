"use strict";

function _typeof(o) { "@babel/helpers - typeof"; return _typeof = "function" == typeof Symbol && "symbol" == typeof Symbol.iterator ? function (o) { return typeof o; } : function (o) { return o && "function" == typeof Symbol && o.constructor === Symbol && o !== Symbol.prototype ? "symbol" : typeof o; }, _typeof(o); }
function _toConsumableArray(r) { return _arrayWithoutHoles(r) || _iterableToArray(r) || _unsupportedIterableToArray(r) || _nonIterableSpread(); }
function _nonIterableSpread() { throw new TypeError("Invalid attempt to spread non-iterable instance.\nIn order to be iterable, non-array objects must have a [Symbol.iterator]() method."); }
function _iterableToArray(r) { if ("undefined" != typeof Symbol && null != r[Symbol.iterator] || null != r["@@iterator"]) return Array.from(r); }
function _arrayWithoutHoles(r) { if (Array.isArray(r)) return _arrayLikeToArray(r); }
function _regeneratorRuntime() { "use strict"; /*! regenerator-runtime -- Copyright (c) 2014-present, Facebook, Inc. -- license (MIT): https://github.com/facebook/regenerator/blob/main/LICENSE */ _regeneratorRuntime = function _regeneratorRuntime() { return e; }; var t, e = {}, r = Object.prototype, n = r.hasOwnProperty, o = Object.defineProperty || function (t, e, r) { t[e] = r.value; }, i = "function" == typeof Symbol ? Symbol : {}, a = i.iterator || "@@iterator", c = i.asyncIterator || "@@asyncIterator", u = i.toStringTag || "@@toStringTag"; function define(t, e, r) { return Object.defineProperty(t, e, { value: r, enumerable: !0, configurable: !0, writable: !0 }), t[e]; } try { define({}, ""); } catch (t) { define = function define(t, e, r) { return t[e] = r; }; } function wrap(t, e, r, n) { var i = e && e.prototype instanceof Generator ? e : Generator, a = Object.create(i.prototype), c = new Context(n || []); return o(a, "_invoke", { value: makeInvokeMethod(t, r, c) }), a; } function tryCatch(t, e, r) { try { return { type: "normal", arg: t.call(e, r) }; } catch (t) { return { type: "throw", arg: t }; } } e.wrap = wrap; var h = "suspendedStart", l = "suspendedYield", f = "executing", s = "completed", y = {}; function Generator() {} function GeneratorFunction() {} function GeneratorFunctionPrototype() {} var p = {}; define(p, a, function () { return this; }); var d = Object.getPrototypeOf, v = d && d(d(values([]))); v && v !== r && n.call(v, a) && (p = v); var g = GeneratorFunctionPrototype.prototype = Generator.prototype = Object.create(p); function defineIteratorMethods(t) { ["next", "throw", "return"].forEach(function (e) { define(t, e, function (t) { return this._invoke(e, t); }); }); } function AsyncIterator(t, e) { function invoke(r, o, i, a) { var c = tryCatch(t[r], t, o); if ("throw" !== c.type) { var u = c.arg, h = u.value; return h && "object" == _typeof(h) && n.call(h, "__await") ? e.resolve(h.__await).then(function (t) { invoke("next", t, i, a); }, function (t) { invoke("throw", t, i, a); }) : e.resolve(h).then(function (t) { u.value = t, i(u); }, function (t) { return invoke("throw", t, i, a); }); } a(c.arg); } var r; o(this, "_invoke", { value: function value(t, n) { function callInvokeWithMethodAndArg() { return new e(function (e, r) { invoke(t, n, e, r); }); } return r = r ? r.then(callInvokeWithMethodAndArg, callInvokeWithMethodAndArg) : callInvokeWithMethodAndArg(); } }); } function makeInvokeMethod(e, r, n) { var o = h; return function (i, a) { if (o === f) throw Error("Generator is already running"); if (o === s) { if ("throw" === i) throw a; return { value: t, done: !0 }; } for (n.method = i, n.arg = a;;) { var c = n.delegate; if (c) { var u = maybeInvokeDelegate(c, n); if (u) { if (u === y) continue; return u; } } if ("next" === n.method) n.sent = n._sent = n.arg;else if ("throw" === n.method) { if (o === h) throw o = s, n.arg; n.dispatchException(n.arg); } else "return" === n.method && n.abrupt("return", n.arg); o = f; var p = tryCatch(e, r, n); if ("normal" === p.type) { if (o = n.done ? s : l, p.arg === y) continue; return { value: p.arg, done: n.done }; } "throw" === p.type && (o = s, n.method = "throw", n.arg = p.arg); } }; } function maybeInvokeDelegate(e, r) { var n = r.method, o = e.iterator[n]; if (o === t) return r.delegate = null, "throw" === n && e.iterator["return"] && (r.method = "return", r.arg = t, maybeInvokeDelegate(e, r), "throw" === r.method) || "return" !== n && (r.method = "throw", r.arg = new TypeError("The iterator does not provide a '" + n + "' method")), y; var i = tryCatch(o, e.iterator, r.arg); if ("throw" === i.type) return r.method = "throw", r.arg = i.arg, r.delegate = null, y; var a = i.arg; return a ? a.done ? (r[e.resultName] = a.value, r.next = e.nextLoc, "return" !== r.method && (r.method = "next", r.arg = t), r.delegate = null, y) : a : (r.method = "throw", r.arg = new TypeError("iterator result is not an object"), r.delegate = null, y); } function pushTryEntry(t) { var e = { tryLoc: t[0] }; 1 in t && (e.catchLoc = t[1]), 2 in t && (e.finallyLoc = t[2], e.afterLoc = t[3]), this.tryEntries.push(e); } function resetTryEntry(t) { var e = t.completion || {}; e.type = "normal", delete e.arg, t.completion = e; } function Context(t) { this.tryEntries = [{ tryLoc: "root" }], t.forEach(pushTryEntry, this), this.reset(!0); } function values(e) { if (e || "" === e) { var r = e[a]; if (r) return r.call(e); if ("function" == typeof e.next) return e; if (!isNaN(e.length)) { var o = -1, i = function next() { for (; ++o < e.length;) if (n.call(e, o)) return next.value = e[o], next.done = !1, next; return next.value = t, next.done = !0, next; }; return i.next = i; } } throw new TypeError(_typeof(e) + " is not iterable"); } return GeneratorFunction.prototype = GeneratorFunctionPrototype, o(g, "constructor", { value: GeneratorFunctionPrototype, configurable: !0 }), o(GeneratorFunctionPrototype, "constructor", { value: GeneratorFunction, configurable: !0 }), GeneratorFunction.displayName = define(GeneratorFunctionPrototype, u, "GeneratorFunction"), e.isGeneratorFunction = function (t) { var e = "function" == typeof t && t.constructor; return !!e && (e === GeneratorFunction || "GeneratorFunction" === (e.displayName || e.name)); }, e.mark = function (t) { return Object.setPrototypeOf ? Object.setPrototypeOf(t, GeneratorFunctionPrototype) : (t.__proto__ = GeneratorFunctionPrototype, define(t, u, "GeneratorFunction")), t.prototype = Object.create(g), t; }, e.awrap = function (t) { return { __await: t }; }, defineIteratorMethods(AsyncIterator.prototype), define(AsyncIterator.prototype, c, function () { return this; }), e.AsyncIterator = AsyncIterator, e.async = function (t, r, n, o, i) { void 0 === i && (i = Promise); var a = new AsyncIterator(wrap(t, r, n, o), i); return e.isGeneratorFunction(r) ? a : a.next().then(function (t) { return t.done ? t.value : a.next(); }); }, defineIteratorMethods(g), define(g, u, "Generator"), define(g, a, function () { return this; }), define(g, "toString", function () { return "[object Generator]"; }), e.keys = function (t) { var e = Object(t), r = []; for (var n in e) r.push(n); return r.reverse(), function next() { for (; r.length;) { var t = r.pop(); if (t in e) return next.value = t, next.done = !1, next; } return next.done = !0, next; }; }, e.values = values, Context.prototype = { constructor: Context, reset: function reset(e) { if (this.prev = 0, this.next = 0, this.sent = this._sent = t, this.done = !1, this.delegate = null, this.method = "next", this.arg = t, this.tryEntries.forEach(resetTryEntry), !e) for (var r in this) "t" === r.charAt(0) && n.call(this, r) && !isNaN(+r.slice(1)) && (this[r] = t); }, stop: function stop() { this.done = !0; var t = this.tryEntries[0].completion; if ("throw" === t.type) throw t.arg; return this.rval; }, dispatchException: function dispatchException(e) { if (this.done) throw e; var r = this; function handle(n, o) { return a.type = "throw", a.arg = e, r.next = n, o && (r.method = "next", r.arg = t), !!o; } for (var o = this.tryEntries.length - 1; o >= 0; --o) { var i = this.tryEntries[o], a = i.completion; if ("root" === i.tryLoc) return handle("end"); if (i.tryLoc <= this.prev) { var c = n.call(i, "catchLoc"), u = n.call(i, "finallyLoc"); if (c && u) { if (this.prev < i.catchLoc) return handle(i.catchLoc, !0); if (this.prev < i.finallyLoc) return handle(i.finallyLoc); } else if (c) { if (this.prev < i.catchLoc) return handle(i.catchLoc, !0); } else { if (!u) throw Error("try statement without catch or finally"); if (this.prev < i.finallyLoc) return handle(i.finallyLoc); } } } }, abrupt: function abrupt(t, e) { for (var r = this.tryEntries.length - 1; r >= 0; --r) { var o = this.tryEntries[r]; if (o.tryLoc <= this.prev && n.call(o, "finallyLoc") && this.prev < o.finallyLoc) { var i = o; break; } } i && ("break" === t || "continue" === t) && i.tryLoc <= e && e <= i.finallyLoc && (i = null); var a = i ? i.completion : {}; return a.type = t, a.arg = e, i ? (this.method = "next", this.next = i.finallyLoc, y) : this.complete(a); }, complete: function complete(t, e) { if ("throw" === t.type) throw t.arg; return "break" === t.type || "continue" === t.type ? this.next = t.arg : "return" === t.type ? (this.rval = this.arg = t.arg, this.method = "return", this.next = "end") : "normal" === t.type && e && (this.next = e), y; }, finish: function finish(t) { for (var e = this.tryEntries.length - 1; e >= 0; --e) { var r = this.tryEntries[e]; if (r.finallyLoc === t) return this.complete(r.completion, r.afterLoc), resetTryEntry(r), y; } }, "catch": function _catch(t) { for (var e = this.tryEntries.length - 1; e >= 0; --e) { var r = this.tryEntries[e]; if (r.tryLoc === t) { var n = r.completion; if ("throw" === n.type) { var o = n.arg; resetTryEntry(r); } return o; } } throw Error("illegal catch attempt"); }, delegateYield: function delegateYield(e, r, n) { return this.delegate = { iterator: values(e), resultName: r, nextLoc: n }, "next" === this.method && (this.arg = t), y; } }, e; }
function ownKeys(e, r) { var t = Object.keys(e); if (Object.getOwnPropertySymbols) { var o = Object.getOwnPropertySymbols(e); r && (o = o.filter(function (r) { return Object.getOwnPropertyDescriptor(e, r).enumerable; })), t.push.apply(t, o); } return t; }
function _objectSpread(e) { for (var r = 1; r < arguments.length; r++) { var t = null != arguments[r] ? arguments[r] : {}; r % 2 ? ownKeys(Object(t), !0).forEach(function (r) { _defineProperty(e, r, t[r]); }) : Object.getOwnPropertyDescriptors ? Object.defineProperties(e, Object.getOwnPropertyDescriptors(t)) : ownKeys(Object(t)).forEach(function (r) { Object.defineProperty(e, r, Object.getOwnPropertyDescriptor(t, r)); }); } return e; }
function _defineProperty(e, r, t) { return (r = _toPropertyKey(r)) in e ? Object.defineProperty(e, r, { value: t, enumerable: !0, configurable: !0, writable: !0 }) : e[r] = t, e; }
function _toPropertyKey(t) { var i = _toPrimitive(t, "string"); return "symbol" == _typeof(i) ? i : i + ""; }
function _toPrimitive(t, r) { if ("object" != _typeof(t) || !t) return t; var e = t[Symbol.toPrimitive]; if (void 0 !== e) { var i = e.call(t, r || "default"); if ("object" != _typeof(i)) return i; throw new TypeError("@@toPrimitive must return a primitive value."); } return ("string" === r ? String : Number)(t); }
function asyncGeneratorStep(n, t, e, r, o, a, c) { try { var i = n[a](c), u = i.value; } catch (n) { return void e(n); } i.done ? t(u) : Promise.resolve(u).then(r, o); }
function _asyncToGenerator(n) { return function () { var t = this, e = arguments; return new Promise(function (r, o) { var a = n.apply(t, e); function _next(n) { asyncGeneratorStep(a, r, o, _next, _throw, "next", n); } function _throw(n) { asyncGeneratorStep(a, r, o, _next, _throw, "throw", n); } _next(void 0); }); }; }
function _slicedToArray(r, e) { return _arrayWithHoles(r) || _iterableToArrayLimit(r, e) || _unsupportedIterableToArray(r, e) || _nonIterableRest(); }
function _nonIterableRest() { throw new TypeError("Invalid attempt to destructure non-iterable instance.\nIn order to be iterable, non-array objects must have a [Symbol.iterator]() method."); }
function _unsupportedIterableToArray(r, a) { if (r) { if ("string" == typeof r) return _arrayLikeToArray(r, a); var t = {}.toString.call(r).slice(8, -1); return "Object" === t && r.constructor && (t = r.constructor.name), "Map" === t || "Set" === t ? Array.from(r) : "Arguments" === t || /^(?:Ui|I)nt(?:8|16|32)(?:Clamped)?Array$/.test(t) ? _arrayLikeToArray(r, a) : void 0; } }
function _arrayLikeToArray(r, a) { (null == a || a > r.length) && (a = r.length); for (var e = 0, n = Array(a); e < a; e++) n[e] = r[e]; return n; }
function _iterableToArrayLimit(r, l) { var t = null == r ? null : "undefined" != typeof Symbol && r[Symbol.iterator] || r["@@iterator"]; if (null != t) { var e, n, i, u, a = [], f = !0, o = !1; try { if (i = (t = t.call(r)).next, 0 === l) { if (Object(t) !== t) return; f = !1; } else for (; !(f = (e = i.call(t)).done) && (a.push(e.value), a.length !== l); f = !0); } catch (r) { o = !0, n = r; } finally { try { if (!f && null != t["return"] && (u = t["return"](), Object(u) !== u)) return; } finally { if (o) throw n; } } return a; } }
function _arrayWithHoles(r) { if (Array.isArray(r)) return r; }
var _React = React,
  useEffect = _React.useEffect,
  useMemo = _React.useMemo,
  useState = _React.useState;
var emptyMetrics = {
  similarAppointments: 0,
  medications: 0,
  quantityNeeded: 0,
  kgEvidence: 0,
  chargeLines: 0,
  expectedTotalCost: 0,
  forecastVisits: 0,
  fourWeekStockItems: 0,
  database: "neo4j"
};
var defaultVendors = ["Amazon", "Chewy", "Covetrus", "MWI", "Patterson", "Med-Vet International"];
function todayPlus(days) {
  var value = new Date();
  value.setDate(value.getDate() + days);
  return value.toISOString().slice(0, 10);
}
function money(value) {
  var number = Number(value || 0);
  if (!Number.isFinite(number)) return "$0.00";
  return number.toLocaleString("en-US", {
    style: "currency",
    currency: "USD"
  });
}
function downloadBlob(blob, filename) {
  var url = URL.createObjectURL(blob);
  var link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}
function fileStem(filters, payload) {
  var vendor = (filters.vendor || "vendor").toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "");
  var period = (payload.appointmentDate || "all_future").replace(/[^a-z0-9]+/gi, "_").replace(/^_|_$/g, "");
  return "florida_plantation_inventory_".concat(vendor, "_").concat(period);
}
function vendorLabel(vendor) {
  return vendor === "Use KG supplier" ? "Recorded supplier" : vendor;
}
function App() {
  var _payload$inventory, _bootstrap$forecastOp, _cartResult$results;
  var _useState = useState(null),
    _useState2 = _slicedToArray(_useState, 2),
    bootstrap = _useState2[0],
    setBootstrap = _useState2[1];
  var _useState3 = useState({
      vendor: "Med-Vet International"
    }),
    _useState4 = _slicedToArray(_useState3, 2),
    filters = _useState4[0],
    setFilters = _useState4[1];
  var _useState5 = useState({
      clinicName: "Florida Plantation Clinic",
      forecastOptions: [],
      inventory: [],
      vendorInvoice: [],
      chargeLines: [],
      inventoryRollup: [],
      evidenceTrail: [],
      provenance: [],
      forecastRules: [],
      metrics: emptyMetrics,
      purchaseDate: todayPlus(5),
      vendor: "Med-Vet International",
      vendorOptions: defaultVendors
    }),
    _useState6 = _slicedToArray(_useState5, 2),
    payload = _useState6[0],
    setPayload = _useState6[1];
  var _useState7 = useState(true),
    _useState8 = _slicedToArray(_useState7, 2),
    loading = _useState8[0],
    setLoading = _useState8[1];
  var _useState9 = useState(""),
    _useState10 = _slicedToArray(_useState9, 2),
    error = _useState10[0],
    setError = _useState10[1];
  var _useState11 = useState(false),
    _useState12 = _slicedToArray(_useState11, 2),
    chatOpen = _useState12[0],
    setChatOpen = _useState12[1];
  var _useState13 = useState(""),
    _useState14 = _slicedToArray(_useState13, 2),
    chatInput = _useState14[0],
    setChatInput = _useState14[1];
  var _useState15 = useState(false),
    _useState16 = _slicedToArray(_useState15, 2),
    chatBusy = _useState16[0],
    setChatBusy = _useState16[1];
  var _useState17 = useState(false),
    _useState18 = _slicedToArray(_useState17, 2),
    cartBusy = _useState18[0],
    setCartBusy = _useState18[1];
  var _useState19 = useState(null),
    _useState20 = _slicedToArray(_useState19, 2),
    cartResult = _useState20[0],
    setCartResult = _useState20[1];
  var _useState21 = useState([{
      role: "assistant",
      content: "Ask why a medication is on the sheet, which past visits support it, or what needs to be ordered."
    }]),
    _useState22 = _slicedToArray(_useState21, 2),
    messages = _useState22[0],
    setMessages = _useState22[1];
  var requestFilters = useMemo(function () {
    return filters;
  }, [filters]);
  var metrics = payload.metrics || emptyMetrics;
  var vendorOptions = (payload.vendorOptions || (bootstrap === null || bootstrap === void 0 ? void 0 : bootstrap.vendorOptions) || defaultVendors).filter(function (vendor) {
    return vendor !== "Use KG supplier";
  });
  var hasRows = ((_payload$inventory = payload.inventory) === null || _payload$inventory === void 0 ? void 0 : _payload$inventory.length) > 0;
  var selectedVendor = payload.vendor || filters.vendor || "Med-Vet International";
  var vendorInvoice = payload.vendorInvoice || [];
  var vendorPreview = vendorInvoice.slice(0, 3);
  var forecastCount = metrics.forecastVisits || (bootstrap === null || bootstrap === void 0 || (_bootstrap$forecastOp = bootstrap.forecastOptions) === null || _bootstrap$forecastOp === void 0 ? void 0 : _bootstrap$forecastOp.length) || 0;
  var forecastPeriod = payload.appointmentDate || "".concat((bootstrap === null || bootstrap === void 0 ? void 0 : bootstrap.minHistoryDate) || "", " to ").concat((bootstrap === null || bootstrap === void 0 ? void 0 : bootstrap.maxHistoryDate) || "");
  var cartStatusLabel = {
    cart_complete: "Cart complete",
    cart_partial: "Cart partially complete",
    cart_stopped: "Cart stopped",
    draft_ready: "Cart draft ready",
    manual_review: "Manual review"
  }[cartResult === null || cartResult === void 0 ? void 0 : cartResult.status] || "Cart update";
  function loadBootstrap() {
    return _loadBootstrap.apply(this, arguments);
  }
  function _loadBootstrap() {
    _loadBootstrap = _asyncToGenerator( /*#__PURE__*/_regeneratorRuntime().mark(function _callee() {
      var response, data;
      return _regeneratorRuntime().wrap(function _callee$(_context) {
        while (1) switch (_context.prev = _context.next) {
          case 0:
            _context.next = 2;
            return fetch("/api/bootstrap");
          case 2:
            response = _context.sent;
            if (response.ok) {
              _context.next = 5;
              break;
            }
            throw new Error("Could not load forecast metadata.");
          case 5:
            _context.next = 7;
            return response.json();
          case 7:
            data = _context.sent;
            setBootstrap(data);
            setFilters(function (current) {
              return _objectSpread(_objectSpread({}, current), {}, {
                vendor: current.vendor || "Med-Vet International"
              });
            });
          case 10:
          case "end":
            return _context.stop();
        }
      }, _callee);
    }));
    return _loadBootstrap.apply(this, arguments);
  }
  function loadInventory() {
    return _loadInventory.apply(this, arguments);
  }
  function _loadInventory() {
    _loadInventory = _asyncToGenerator( /*#__PURE__*/_regeneratorRuntime().mark(function _callee2() {
      var nextFilters,
        response,
        data,
        _args2 = arguments;
      return _regeneratorRuntime().wrap(function _callee2$(_context2) {
        while (1) switch (_context2.prev = _context2.next) {
          case 0:
            nextFilters = _args2.length > 0 && _args2[0] !== undefined ? _args2[0] : requestFilters;
            setLoading(true);
            setError("");
            _context2.prev = 3;
            _context2.next = 6;
            return fetch("/api/inventory", {
              method: "POST",
              headers: {
                "Content-Type": "application/json"
              },
              body: JSON.stringify(nextFilters)
            });
          case 6:
            response = _context2.sent;
            if (response.ok) {
              _context2.next = 9;
              break;
            }
            throw new Error("Could not build the forecast charge sheet.");
          case 9:
            _context2.next = 11;
            return response.json();
          case 11:
            data = _context2.sent;
            setPayload(data);
            _context2.next = 18;
            break;
          case 15:
            _context2.prev = 15;
            _context2.t0 = _context2["catch"](3);
            setError(_context2.t0.message || "Unexpected error");
          case 18:
            _context2.prev = 18;
            setLoading(false);
            return _context2.finish(18);
          case 21:
          case "end":
            return _context2.stop();
        }
      }, _callee2, null, [[3, 15, 18, 21]]);
    }));
    return _loadInventory.apply(this, arguments);
  }
  useEffect(function () {
    loadBootstrap()["catch"](function (err) {
      setError(err.message || "Could not initialize app.");
      setLoading(false);
    });
  }, []);
  useEffect(function () {
    loadInventory(filters);
  }, [filters.vendor]);
  function updateFilter(name, value) {
    if (name === "vendor") setCartResult(null);
    setFilters(function (current) {
      return _objectSpread(_objectSpread({}, current), {}, _defineProperty({}, name, value));
    });
  }
  function exportSheet(_x) {
    return _exportSheet.apply(this, arguments);
  }
  function _exportSheet() {
    _exportSheet = _asyncToGenerator( /*#__PURE__*/_regeneratorRuntime().mark(function _callee3(type) {
      var response, blob;
      return _regeneratorRuntime().wrap(function _callee3$(_context3) {
        while (1) switch (_context3.prev = _context3.next) {
          case 0:
            _context3.next = 2;
            return fetch("/api/export/".concat(type), {
              method: "POST",
              headers: {
                "Content-Type": "application/json"
              },
              body: JSON.stringify(requestFilters)
            });
          case 2:
            response = _context3.sent;
            if (response.ok) {
              _context3.next = 6;
              break;
            }
            setError("Could not export ".concat(type.toUpperCase(), "."));
            return _context3.abrupt("return");
          case 6:
            _context3.next = 8;
            return response.blob();
          case 8:
            blob = _context3.sent;
            downloadBlob(blob, "".concat(fileStem(filters, payload), ".").concat(type === "xlsx" ? "xlsx" : type));
          case 10:
          case "end":
            return _context3.stop();
        }
      }, _callee3);
    }));
    return _exportSheet.apply(this, arguments);
  }
  function sendMessage(_x2) {
    return _sendMessage.apply(this, arguments);
  }
  function _sendMessage() {
    _sendMessage = _asyncToGenerator( /*#__PURE__*/_regeneratorRuntime().mark(function _callee4(event) {
      var question, nextMessages, response, data;
      return _regeneratorRuntime().wrap(function _callee4$(_context4) {
        while (1) switch (_context4.prev = _context4.next) {
          case 0:
            event.preventDefault();
            question = chatInput.trim();
            if (!(!question || chatBusy)) {
              _context4.next = 4;
              break;
            }
            return _context4.abrupt("return");
          case 4:
            nextMessages = [].concat(_toConsumableArray(messages), [{
              role: "user",
              content: question
            }]);
            setMessages(nextMessages);
            setChatInput("");
            setChatBusy(true);
            _context4.prev = 8;
            _context4.next = 11;
            return fetch("/api/chat", {
              method: "POST",
              headers: {
                "Content-Type": "application/json"
              },
              body: JSON.stringify({
                message: question,
                filters: requestFilters,
                history: nextMessages
              })
            });
          case 11:
            response = _context4.sent;
            if (response.ok) {
              _context4.next = 14;
              break;
            }
            throw new Error("Chat request failed.");
          case 14:
            _context4.next = 16;
            return response.json();
          case 16:
            data = _context4.sent;
            setMessages(function (current) {
              return [].concat(_toConsumableArray(current), [{
                role: "assistant",
                content: data.answer,
                source: data.source
              }]);
            });
            _context4.next = 23;
            break;
          case 20:
            _context4.prev = 20;
            _context4.t0 = _context4["catch"](8);
            setMessages(function (current) {
              return [].concat(_toConsumableArray(current), [{
                role: "assistant",
                content: _context4.t0.message || "The chat loop failed.",
                source: "error"
              }]);
            });
          case 23:
            _context4.prev = 23;
            setChatBusy(false);
            return _context4.finish(23);
          case 26:
          case "end":
            return _context4.stop();
        }
      }, _callee4, null, [[8, 20, 23, 26]]);
    }));
    return _sendMessage.apply(this, arguments);
  }
  function createVendorCart() {
    return _createVendorCart.apply(this, arguments);
  }
  function _createVendorCart() {
    _createVendorCart = _asyncToGenerator( /*#__PURE__*/_regeneratorRuntime().mark(function _callee5() {
      var automate,
        visible,
        response,
        _args5 = arguments;
      return _regeneratorRuntime().wrap(function _callee5$(_context5) {
        while (1) switch (_context5.prev = _context5.next) {
          case 0:
            automate = _args5.length > 0 && _args5[0] !== undefined ? _args5[0] : false;
            visible = _args5.length > 1 && _args5[1] !== undefined ? _args5[1] : false;
            setCartBusy(true);
            setCartResult(null);
            setError("");
            _context5.prev = 5;
            _context5.next = 8;
            return fetch("/api/vendor-cart", {
              method: "POST",
              headers: {
                "Content-Type": "application/json"
              },
              body: JSON.stringify({
                filters: requestFilters,
                itemLimit: 3,
                automate: automate,
                visible: visible
              })
            });
          case 8:
            response = _context5.sent;
            if (response.ok) {
              _context5.next = 11;
              break;
            }
            throw new Error("Could not create vendor cart draft.");
          case 11:
            _context5.t0 = setCartResult;
            _context5.next = 14;
            return response.json();
          case 14:
            _context5.t1 = _context5.sent;
            (0, _context5.t0)(_context5.t1);
            _context5.next = 21;
            break;
          case 18:
            _context5.prev = 18;
            _context5.t2 = _context5["catch"](5);
            setError(_context5.t2.message || "Vendor cart request failed.");
          case 21:
            _context5.prev = 21;
            setCartBusy(false);
            return _context5.finish(21);
          case 24:
          case "end":
            return _context5.stop();
        }
      }, _callee5, null, [[5, 18, 21, 24]]);
    }));
    return _createVendorCart.apply(this, arguments);
  }
  return /*#__PURE__*/React.createElement("main", null, /*#__PURE__*/React.createElement("section", {
    className: "hero"
  }, /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    className: "eyebrow"
  }, payload.clinicName || "Florida Plantation Clinic"), /*#__PURE__*/React.createElement("h1", null, "Medication Inventory"))), /*#__PURE__*/React.createElement("section", {
    className: "controls"
  }, /*#__PURE__*/React.createElement("div", {
    className: "controlHeading"
  }, "Inventory Settings"), /*#__PURE__*/React.createElement("div", {
    className: "targetGrid"
  }, /*#__PURE__*/React.createElement("div", {
    className: "scopeCard"
  }, /*#__PURE__*/React.createElement("b", null, "Forecast Period"), /*#__PURE__*/React.createElement("span", null, forecastPeriod || "-")), /*#__PURE__*/React.createElement("label", null, "Vendor", /*#__PURE__*/React.createElement("select", {
    value: filters.vendor,
    onChange: function onChange(event) {
      return updateFilter("vendor", event.target.value);
    }
  }, vendorOptions.map(function (vendor) {
    return /*#__PURE__*/React.createElement("option", {
      key: vendor,
      value: vendor
    }, vendorLabel(vendor));
  })))), /*#__PURE__*/React.createElement("div", {
    className: "appointmentSummary"
  }, /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("b", null, "Clinic"), /*#__PURE__*/React.createElement("span", null, payload.clinicName || "Florida Plantation Clinic")), /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("b", null, "Period"), /*#__PURE__*/React.createElement("span", null, forecastPeriod || "-")), /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("b", null, "Demand"), /*#__PURE__*/React.createElement("span", null, metrics.quantityNeeded || 0, " units")), /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("b", null, "Vendor"), /*#__PURE__*/React.createElement("span", null, vendorLabel(selectedVendor))))), error ? /*#__PURE__*/React.createElement("div", {
    className: "error"
  }, error) : null, /*#__PURE__*/React.createElement("section", {
    className: "metrics"
  }, /*#__PURE__*/React.createElement(Metric, {
    label: "Appointments",
    value: forecastCount,
    detail: "scheduled visits",
    color: "#17437a"
  }), /*#__PURE__*/React.createElement(Metric, {
    label: "Inventory rows",
    value: metrics.medications,
    detail: "".concat(metrics.quantityNeeded || 0, " units to prepare"),
    color: "#17437a"
  }), /*#__PURE__*/React.createElement(Metric, {
    label: "Expected billing",
    value: money(metrics.expectedTotalCost),
    detail: "estimated total",
    color: "#17437a",
    small: true
  })), /*#__PURE__*/React.createElement("section", {
    className: "sheetTop"
  }, /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("h2", null, "Inventory Sheet"))), /*#__PURE__*/React.createElement("section", {
    className: "sheet"
  }, /*#__PURE__*/React.createElement("div", {
    className: "sheetHeader"
  }, /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("h3", null, "Medication Inventory Tracker")), /*#__PURE__*/React.createElement("strong", null, "Purchase date ", payload.purchaseDate)), /*#__PURE__*/React.createElement("div", {
    className: "metaRows"
  }, /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("b", null, "Clinic"), /*#__PURE__*/React.createElement("span", null, payload.clinicName)), /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("b", null, "Period"), /*#__PURE__*/React.createElement("span", null, forecastPeriod)), /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("b", null, "Appointments"), /*#__PURE__*/React.createElement("span", null, forecastCount)), /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("b", null, "Vendor"), /*#__PURE__*/React.createElement("span", null, vendorLabel(selectedVendor)))), /*#__PURE__*/React.createElement(InventoryTable, {
    rows: payload.inventory || [],
    loading: loading
  }), /*#__PURE__*/React.createElement("div", {
    className: "sheetExport"
  }, /*#__PURE__*/React.createElement("div", {
    className: "exportTitle"
  }, "Export inventory sheet"), /*#__PURE__*/React.createElement("div", {
    className: "exportActions"
  }, /*#__PURE__*/React.createElement("button", {
    disabled: !hasRows,
    onClick: function onClick() {
      return exportSheet("pdf");
    }
  }, "PDF"), /*#__PURE__*/React.createElement("button", {
    disabled: !hasRows,
    onClick: function onClick() {
      return exportSheet("xlsx");
    }
  }, "Excel"), /*#__PURE__*/React.createElement("button", {
    disabled: !hasRows,
    onClick: function onClick() {
      return exportSheet("csv");
    }
  }, "CSV")))), /*#__PURE__*/React.createElement("section", {
    className: "evidence"
  }, /*#__PURE__*/React.createElement(EvidenceCards, {
    rows: payload.evidenceTrail || []
  })), /*#__PURE__*/React.createElement("section", {
    className: "vendorPanel"
  }, /*#__PURE__*/React.createElement("div", {
    className: "vendorToolbar"
  }, /*#__PURE__*/React.createElement("div", {
    className: "vendorSelector"
  }, /*#__PURE__*/React.createElement("b", null, vendorLabel(selectedVendor), " invoice"), /*#__PURE__*/React.createElement("span", null, "Showing ", Math.min(3, vendorInvoice.length || 0), " of ", vendorInvoice.length || 0, " rows \xB7 ", payload.vendorWebsite || "recorded supplier"))), /*#__PURE__*/React.createElement(VendorInvoiceTable, {
    rows: vendorPreview
  }), /*#__PURE__*/React.createElement("div", {
    className: "vendorActions"
  }, /*#__PURE__*/React.createElement("button", {
    disabled: !hasRows || cartBusy,
    onClick: function onClick() {
      return createVendorCart(false, false);
    }
  }, "Create cart draft"), /*#__PURE__*/React.createElement("button", {
    disabled: !hasRows || cartBusy,
    onClick: function onClick() {
      return createVendorCart(true, true);
    }
  }, "Open website and add cart")), cartResult ? /*#__PURE__*/React.createElement("div", {
    className: "cartResult ".concat(cartResult.status || "")
  }, /*#__PURE__*/React.createElement("b", null, cartStatusLabel), /*#__PURE__*/React.createElement("span", null, cartResult.message), (_cartResult$results = cartResult.results) !== null && _cartResult$results !== void 0 && _cartResult$results.length ? /*#__PURE__*/React.createElement("div", {
    className: "cartResultList"
  }, /*#__PURE__*/React.createElement("span", null, "Confirmed: ", cartResult.results.filter(function (row) {
    return String(row.status || "").startsWith("added_to_cart");
  }).map(function (row) {
    return row["Medication Name"];
  }).join(", ") || "No additions confirmed yet")) : null) : null), /*#__PURE__*/React.createElement(ChatWidget, {
    open: chatOpen,
    setOpen: setChatOpen,
    messages: messages,
    chatInput: chatInput,
    setChatInput: setChatInput,
    sendMessage: sendMessage,
    busy: chatBusy
  }));
}
function Metric(_ref) {
  var label = _ref.label,
    value = _ref.value,
    detail = _ref.detail,
    color = _ref.color,
    _ref$small = _ref.small,
    small = _ref$small === void 0 ? false : _ref$small;
  return /*#__PURE__*/React.createElement("div", {
    className: "metric",
    style: {
      borderTopColor: color
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "metricLabel"
  }, label), /*#__PURE__*/React.createElement("div", {
    className: small ? "metricValue small" : "metricValue"
  }, value), /*#__PURE__*/React.createElement("div", {
    className: "metricDetail"
  }, detail));
}
function InventoryTable(_ref2) {
  var rows = _ref2.rows,
    _ref2$loading = _ref2.loading,
    loading = _ref2$loading === void 0 ? false : _ref2$loading;
  var headers = ["Medication Name", "Product Type", "Quantity Needed", "Expected Units", "Unit Size", "Forecasted Appointments", "Date To Purchase", "Supplier or Store", "Expected Cost"];
  return /*#__PURE__*/React.createElement("div", {
    className: "tableWrap"
  }, /*#__PURE__*/React.createElement("table", null, /*#__PURE__*/React.createElement("thead", null, /*#__PURE__*/React.createElement("tr", null, headers.map(function (header) {
    return /*#__PURE__*/React.createElement("th", {
      key: header
    }, header);
  }))), /*#__PURE__*/React.createElement("tbody", null, loading ? /*#__PURE__*/React.createElement("tr", null, /*#__PURE__*/React.createElement("td", {
    colSpan: headers.length
  }, "Building inventory sheet from forecasted invoice lines...")) : rows.length ? rows.map(function (row, index) {
    return /*#__PURE__*/React.createElement("tr", {
      key: "".concat(row["Medication Name"], "-").concat(index)
    }, headers.map(function (header) {
      return /*#__PURE__*/React.createElement("td", {
        key: header
      }, row[header] || "");
    }));
  }) : /*#__PURE__*/React.createElement("tr", null, /*#__PURE__*/React.createElement("td", {
    colSpan: headers.length
  }, "No stockable medication rows were predicted for upcoming appointments.")))));
}
function VendorInvoiceTable(_ref3) {
  var rows = _ref3.rows;
  var headers = ["Medication Name", "Quantity", "Unit Size", "Price", "Cart Status"];
  return /*#__PURE__*/React.createElement("div", {
    className: "vendorInvoiceTable"
  }, /*#__PURE__*/React.createElement("table", null, /*#__PURE__*/React.createElement("thead", null, /*#__PURE__*/React.createElement("tr", null, headers.map(function (header) {
    return /*#__PURE__*/React.createElement("th", {
      key: header
    }, header);
  }))), /*#__PURE__*/React.createElement("tbody", null, rows.length ? rows.map(function (row) {
    return /*#__PURE__*/React.createElement("tr", {
      key: "".concat(row.Line, "-").concat(row["Medication Name"])
    }, headers.map(function (header) {
      return /*#__PURE__*/React.createElement("td", {
        key: header
      }, row[header] || "");
    }));
  }) : /*#__PURE__*/React.createElement("tr", null, /*#__PURE__*/React.createElement("td", {
    colSpan: headers.length
  }, "No vendor invoice rows are available yet.")))));
}
function EvidenceCards(_ref4) {
  var rows = _ref4.rows;
  var cards = (rows || []).slice(0, 3);
  if (!cards.length) {
    return /*#__PURE__*/React.createElement("section", {
      className: "evidenceCards"
    }, /*#__PURE__*/React.createElement("div", {
      className: "evidenceCard"
    }, /*#__PURE__*/React.createElement("b", null, "Evidence"), /*#__PURE__*/React.createElement("p", null, "No evidence rows are available.")));
  }
  return /*#__PURE__*/React.createElement("section", {
    className: "evidenceCards"
  }, cards.map(function (row, index) {
    return /*#__PURE__*/React.createElement("article", {
      className: "evidenceCard",
      key: "".concat(row["Future Appointment"], "-").concat(row["Past Appointment"], "-").concat(index)
    }, /*#__PURE__*/React.createElement("div", {
      className: "evidenceCardTop"
    }, /*#__PURE__*/React.createElement("b", null, row["Future Pet"] || row["Future Appointment"]), /*#__PURE__*/React.createElement("span", null, row["Future Date"], " \xB7 similarity ", row.Similarity)), /*#__PURE__*/React.createElement("div", {
      className: "evidencePair"
    }, /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("small", null, "Future complaint"), /*#__PURE__*/React.createElement("p", null, row["Future Complaint"] || "-")), /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("small", null, "Matched invoice visit"), /*#__PURE__*/React.createElement("p", null, row["Past Appointment"], " \xB7 ", row["Past Date"]))), /*#__PURE__*/React.createElement("div", {
      className: "invoiceSnippet"
    }, /*#__PURE__*/React.createElement("small", null, "Invoice evidence"), /*#__PURE__*/React.createElement("p", null, row["Invoice Items"] || "-")));
  }));
}
function EvidenceTable(_ref5) {
  var title = _ref5.title,
    rows = _ref5.rows;
  var headers = rows[0] ? Object.keys(rows[0]).filter(function (header) {
    return !header.startsWith("_");
  }) : [];
  return /*#__PURE__*/React.createElement("div", {
    className: "evidencePanel"
  }, /*#__PURE__*/React.createElement("h4", null, title), /*#__PURE__*/React.createElement("div", {
    className: "tableWrap compact"
  }, /*#__PURE__*/React.createElement("table", null, /*#__PURE__*/React.createElement("thead", null, /*#__PURE__*/React.createElement("tr", null, headers.map(function (header) {
    return /*#__PURE__*/React.createElement("th", {
      key: header
    }, header.replaceAll("_", " "));
  }))), /*#__PURE__*/React.createElement("tbody", null, rows.length ? rows.slice(0, 60).map(function (row, index) {
    return /*#__PURE__*/React.createElement("tr", {
      key: index
    }, headers.map(function (header) {
      var _row$header;
      return /*#__PURE__*/React.createElement("td", {
        key: header
      }, String((_row$header = row[header]) !== null && _row$header !== void 0 ? _row$header : ""));
    }));
  }) : /*#__PURE__*/React.createElement("tr", null, /*#__PURE__*/React.createElement("td", null, "No evidence rows."))))));
}
function ChatWidget(_ref6) {
  var open = _ref6.open,
    setOpen = _ref6.setOpen,
    messages = _ref6.messages,
    chatInput = _ref6.chatInput,
    setChatInput = _ref6.setChatInput,
    sendMessage = _ref6.sendMessage,
    busy = _ref6.busy;
  function sourceLabel(source) {
    if (source === "kg-fast-cache") return "Cached data";
    if (source === "kg-fast") return "Data";
    if (source === "codex") return "Codex";
    return source;
  }
  return /*#__PURE__*/React.createElement(React.Fragment, null, open ? /*#__PURE__*/React.createElement("aside", {
    className: "chatPanel"
  }, /*#__PURE__*/React.createElement("div", {
    className: "chatHeader"
  }, /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("strong", null, "Inventory assistant"), /*#__PURE__*/React.createElement("span", null, "Ask why, quantity, vendor, or evidence questions")), /*#__PURE__*/React.createElement("button", {
    onClick: function onClick() {
      return setOpen(false);
    },
    "aria-label": "Close chat"
  }, "x")), /*#__PURE__*/React.createElement("div", {
    className: "chatMessages"
  }, messages.map(function (message, index) {
    return /*#__PURE__*/React.createElement("div", {
      className: "message ".concat(message.role),
      key: index
    }, /*#__PURE__*/React.createElement("b", null, message.role === "user" ? "You" : "Assistant"), /*#__PURE__*/React.createElement("p", null, message.content), message.source ? /*#__PURE__*/React.createElement("small", null, sourceLabel(message.source)) : null);
  }), busy ? /*#__PURE__*/React.createElement("div", {
    className: "message assistant"
  }, /*#__PURE__*/React.createElement("b", null, "Assistant"), /*#__PURE__*/React.createElement("p", null, "Checking forecast evidence...")) : null), /*#__PURE__*/React.createElement("form", {
    className: "chatForm",
    onSubmit: sendMessage
  }, /*#__PURE__*/React.createElement("input", {
    value: chatInput,
    onChange: function onChange(event) {
      return setChatInput(event.target.value);
    },
    placeholder: "Why is Gabapentin here?"
  }), /*#__PURE__*/React.createElement("button", {
    disabled: busy || !chatInput.trim()
  }, "Ask"))) : null, /*#__PURE__*/React.createElement("button", {
    className: "chatLauncher",
    onClick: function onClick() {
      return setOpen(function (value) {
        return !value;
      });
    },
    "aria-label": "Open inventory chat"
  }, /*#__PURE__*/React.createElement("span", {
    className: "chatIcon"
  }), "Chat"));
}
ReactDOM.createRoot(document.getElementById("root")).render( /*#__PURE__*/React.createElement(App, null));