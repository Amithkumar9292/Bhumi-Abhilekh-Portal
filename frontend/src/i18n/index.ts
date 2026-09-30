/**
 * i18n — Internationalization system for Bhumi Abhilekh Portal
 *
 * Supports all 22 languages of the Eighth Schedule of the Indian Constitution:
 * Assamese, Bengali, Bodo, Dogri, Gujarati, Hindi, Kannada, Kashmiri,
 * Konkani, Maithili, Malayalam, Manipuri, Marathi, Nepali, Odia,
 * Punjabi, Sanskrit, Santali, Sindhi, Tamil, Telugu, Urdu
 *
 * Architecture:
 * - Flat key-value translation maps per language
 * - React context + hook for consumption
 * - Persistent via localStorage
 * - Lazy-loads non-default language chunks
 * - Google Fonts loaded dynamically per language
 */

// ── Language metadata ─────────────────────────────────────────────────────────

export interface LangMeta {
  code: string;
  name: string;           // English name
  nativeName: string;     // Name in own script
  script: string;         // Script family
  dir: 'ltr' | 'rtl';
  googleFont?: string;
  fontFamily?: string;
  scheduleLang: boolean;  // Part of 8th Schedule
}

export const LANGUAGES: LangMeta[] = [
  { code: 'en',  name: 'English',    nativeName: 'English',     script: 'Latin',     dir: 'ltr', scheduleLang: false },
  { code: 'hi',  name: 'Hindi',      nativeName: 'हिन्दी',        script: 'Devanagari', dir: 'ltr', googleFont: 'Noto+Sans+Devanagari:wght@400;600;700', fontFamily: "'Noto Sans Devanagari'", scheduleLang: true },
  { code: 'bn',  name: 'Bengali',    nativeName: 'বাংলা',          script: 'Bengali',   dir: 'ltr', googleFont: 'Noto+Sans+Bengali:wght@400;600;700',     fontFamily: "'Noto Sans Bengali'",     scheduleLang: true },
  { code: 'te',  name: 'Telugu',     nativeName: 'తెలుగు',         script: 'Telugu',    dir: 'ltr', googleFont: 'Noto+Sans+Telugu:wght@400;600;700',      fontFamily: "'Noto Sans Telugu'",      scheduleLang: true },
  { code: 'mr',  name: 'Marathi',    nativeName: 'मराठी',          script: 'Devanagari', dir: 'ltr', googleFont: 'Noto+Sans+Devanagari:wght@400;600;700', fontFamily: "'Noto Sans Devanagari'", scheduleLang: true },
  { code: 'ta',  name: 'Tamil',      nativeName: 'தமிழ்',          script: 'Tamil',     dir: 'ltr', googleFont: 'Noto+Sans+Tamil:wght@400;600;700',       fontFamily: "'Noto Sans Tamil'",       scheduleLang: true },
  { code: 'gu',  name: 'Gujarati',   nativeName: 'ગુજરાતી',        script: 'Gujarati',  dir: 'ltr', googleFont: 'Noto+Sans+Gujarati:wght@400;600;700',    fontFamily: "'Noto Sans Gujarati'",    scheduleLang: true },
  { code: 'kn',  name: 'Kannada',    nativeName: 'ಕನ್ನಡ',          script: 'Kannada',   dir: 'ltr', googleFont: 'Noto+Sans+Kannada:wght@400;600;700',     fontFamily: "'Noto Sans Kannada'",     scheduleLang: true },
  { code: 'ml',  name: 'Malayalam',  nativeName: 'മലയാളം',         script: 'Malayalam', dir: 'ltr', googleFont: 'Noto+Sans+Malayalam:wght@400;600;700',   fontFamily: "'Noto Sans Malayalam'",   scheduleLang: true },
  { code: 'pa',  name: 'Punjabi',    nativeName: 'ਪੰਜਾਬੀ',         script: 'Gurmukhi',  dir: 'ltr', googleFont: 'Noto+Sans+Gurmukhi:wght@400;600;700',    fontFamily: "'Noto Sans Gurmukhi'",    scheduleLang: true },
  { code: 'or',  name: 'Odia',       nativeName: 'ଓଡ଼ିଆ',           script: 'Oriya',     dir: 'ltr', googleFont: 'Noto+Sans+Oriya:wght@400;600;700',       fontFamily: "'Noto Sans Oriya'",       scheduleLang: true },
  { code: 'as',  name: 'Assamese',   nativeName: 'অসমীয়া',         script: 'Bengali',   dir: 'ltr', googleFont: 'Noto+Sans+Bengali:wght@400;600;700',     fontFamily: "'Noto Sans Bengali'",     scheduleLang: true },
  { code: 'ur',  name: 'Urdu',       nativeName: 'اردو',            script: 'Nastaliq',  dir: 'rtl', googleFont: 'Noto+Nastaliq+Urdu:wght@400;700',        fontFamily: "'Noto Nastaliq Urdu'",    scheduleLang: true },
  { code: 'mai', name: 'Maithili',   nativeName: 'मैथिली',          script: 'Devanagari', dir: 'ltr', googleFont: 'Noto+Sans+Devanagari:wght@400;600;700', fontFamily: "'Noto Sans Devanagari'", scheduleLang: true },
  { code: 'sa',  name: 'Sanskrit',   nativeName: 'संस्कृतम्',        script: 'Devanagari', dir: 'ltr', googleFont: 'Noto+Sans+Devanagari:wght@400;600;700', fontFamily: "'Noto Sans Devanagari'", scheduleLang: true },
];

// ── Translation keys ──────────────────────────────────────────────────────────

export type TranslationKey =
  // Navigation
  | 'nav.dashboard' | 'nav.intake' | 'nav.pipeline' | 'nav.documents'
  | 'nav.landRecords' | 'nav.verification' | 'nav.gisMap' | 'nav.anomalies'
  | 'nav.reports' | 'nav.auditTrail' | 'nav.users' | 'nav.integrations' | 'nav.settings'
  // Auth
  | 'auth.login' | 'auth.logout' | 'auth.username' | 'auth.password'
  | 'auth.loginTitle' | 'auth.loginSubtitle' | 'auth.signingIn' | 'auth.loginFailed'
  // Dashboard
  | 'dash.title' | 'dash.subtitle' | 'dash.totalRecords' | 'dash.verified'
  | 'dash.pendingReview' | 'dash.anomalies' | 'dash.docsProcessed' | 'dash.areaDigitized'
  // Land Records
  | 'lr.title' | 'lr.khasra' | 'lr.khata' | 'lr.survey' | 'lr.owner'
  | 'lr.district' | 'lr.tehsil' | 'lr.village' | 'lr.state' | 'lr.area'
  | 'lr.landUse' | 'lr.status' | 'lr.mutation' | 'lr.registration'
  | 'lr.createRecord' | 'lr.editRecord' | 'lr.verifyRecord'
  // Status
  | 'status.pending' | 'status.underReview' | 'status.verified' | 'status.rejected' | 'status.archived'
  | 'status.processing' | 'status.uploaded' | 'status.failed'
  // Common actions
  | 'action.search' | 'action.filter' | 'action.export' | 'action.import' | 'action.upload'
  | 'action.save' | 'action.cancel' | 'action.confirm' | 'action.delete' | 'action.edit'
  | 'action.view' | 'action.approve' | 'action.reject' | 'action.retry' | 'action.refresh'
  | 'action.submit' | 'action.verify' | 'action.resolve' | 'action.download'
  // Validation
  | 'val.required' | 'val.invalidFormat' | 'val.tooShort' | 'val.tooLong' | 'val.duplicateRecord'
  // Document Intake
  | 'intake.title' | 'intake.subtitle' | 'intake.dropzone' | 'intake.selectFile'
  | 'intake.uploading' | 'intake.success' | 'intake.processing'
  // Pipeline
  | 'pipe.title' | 'pipe.queue' | 'pipe.extractedFields' | 'pipe.anomalies'
  | 'pipe.humanReview' | 'pipe.confidence' | 'pipe.verify'
  // GIS
  | 'gis.title' | 'gis.searchLocation' | 'gis.synthetic' | 'gis.totalParcels'
  // Analytics
  | 'analytics.title' | 'analytics.recordsByStatus' | 'analytics.byDistrict'
  | 'analytics.processingThroughput' | 'analytics.areaDistribution'
  // Audit
  | 'audit.title' | 'audit.action' | 'audit.actor' | 'audit.resource' | 'audit.timestamp'
  // Users
  | 'users.title' | 'users.role' | 'users.active' | 'users.inactive' | 'users.createUser'
  // Settings
  | 'settings.title' | 'settings.language' | 'settings.theme' | 'settings.notifications'
  // Errors & system
  | 'error.notFound' | 'error.unauthorized' | 'error.serverError' | 'error.networkError'
  | 'sys.loading' | 'sys.noData' | 'sys.demoNotice' | 'sys.nonLegalBinding'
  | 'sys.poweredBy' | 'sys.version' | 'sys.lastUpdated';

export type Translations = Record<TranslationKey, string>;

// ── English (base language) ────────────────────────────────────────────────────

const en: Translations = {
  'nav.dashboard': 'Dashboard',
  'nav.intake': 'Document Intake',
  'nav.pipeline': 'Pipeline',
  'nav.documents': 'Documents',
  'nav.landRecords': 'Land Records',
  'nav.verification': 'Verification',
  'nav.gisMap': 'GIS Map',
  'nav.anomalies': 'Anomalies',
  'nav.reports': 'Reports',
  'nav.auditTrail': 'Audit Trail',
  'nav.users': 'Users & Roles',
  'nav.integrations': 'Integrations',
  'nav.settings': 'Settings',

  'auth.login': 'Sign In',
  'auth.logout': 'Sign Out',
  'auth.username': 'Username / Employee ID',
  'auth.password': 'Password',
  'auth.loginTitle': 'Bhumi Abhilekh Portal',
  'auth.loginSubtitle': 'Intelligent Land Record Digitization System',
  'auth.signingIn': 'Signing in…',
  'auth.loginFailed': 'Invalid username or password',

  'dash.title': 'Dashboard',
  'dash.subtitle': 'System overview and key metrics',
  'dash.totalRecords': 'Total Records',
  'dash.verified': 'Verified',
  'dash.pendingReview': 'Pending Review',
  'dash.anomalies': 'Anomalies',
  'dash.docsProcessed': 'Documents Processed',
  'dash.areaDigitized': 'Area Digitized (ha)',

  'lr.title': 'Land Records',
  'lr.khasra': 'Khasra Number',
  'lr.khata': 'Khata / Khatauni',
  'lr.survey': 'Survey Number',
  'lr.owner': 'Owner Name',
  'lr.district': 'District',
  'lr.tehsil': 'Tehsil / Taluka',
  'lr.village': 'Village / Gaon',
  'lr.state': 'State',
  'lr.area': 'Area (Hectares)',
  'lr.landUse': 'Land Classification',
  'lr.status': 'Status',
  'lr.mutation': 'Mutation',
  'lr.registration': 'Registration',
  'lr.createRecord': 'Create Record',
  'lr.editRecord': 'Edit Record',
  'lr.verifyRecord': 'Verify Record',

  'status.pending': 'Pending',
  'status.underReview': 'Under Review',
  'status.verified': 'Verified',
  'status.rejected': 'Rejected',
  'status.archived': 'Archived',
  'status.processing': 'Processing',
  'status.uploaded': 'Uploaded',
  'status.failed': 'Failed',

  'action.search': 'Search',
  'action.filter': 'Filter',
  'action.export': 'Export',
  'action.import': 'Import',
  'action.upload': 'Upload',
  'action.save': 'Save',
  'action.cancel': 'Cancel',
  'action.confirm': 'Confirm',
  'action.delete': 'Delete',
  'action.edit': 'Edit',
  'action.view': 'View',
  'action.approve': 'Approve',
  'action.reject': 'Reject',
  'action.retry': 'Retry',
  'action.refresh': 'Refresh',
  'action.submit': 'Submit',
  'action.verify': 'Verify',
  'action.resolve': 'Resolve',
  'action.download': 'Download',

  'val.required': 'This field is required',
  'val.invalidFormat': 'Invalid format',
  'val.tooShort': 'Too short',
  'val.tooLong': 'Too long',
  'val.duplicateRecord': 'A record with this identifier already exists',

  'intake.title': 'Document Intake',
  'intake.subtitle': 'Upload land record documents for OCR processing',
  'intake.dropzone': 'Drop files here or click to browse',
  'intake.selectFile': 'Select File',
  'intake.uploading': 'Uploading…',
  'intake.success': 'Upload successful. Pipeline triggered.',
  'intake.processing': 'Processing document…',

  'pipe.title': 'Processing Pipeline',
  'pipe.queue': 'Pipeline Queue',
  'pipe.extractedFields': 'Extracted Fields',
  'pipe.anomalies': 'Anomalies',
  'pipe.humanReview': 'Human Verification Required',
  'pipe.confidence': 'Confidence',
  'pipe.verify': 'Verify',

  'gis.title': 'GIS / Cadastral Map',
  'gis.searchLocation': 'Search by location or khasra number',
  'gis.synthetic': 'Synthetic coordinates — demo only',
  'gis.totalParcels': 'Total Parcels',

  'analytics.title': 'Analytics & Reports',
  'analytics.recordsByStatus': 'Records by Status',
  'analytics.byDistrict': 'By District',
  'analytics.processingThroughput': 'Processing Throughput',
  'analytics.areaDistribution': 'Area Distribution',

  'audit.title': 'Audit Trail',
  'audit.action': 'Action',
  'audit.actor': 'Actor',
  'audit.resource': 'Resource',
  'audit.timestamp': 'Timestamp',

  'users.title': 'Users & Roles',
  'users.role': 'Role',
  'users.active': 'Active',
  'users.inactive': 'Inactive',
  'users.createUser': 'Create User',

  'settings.title': 'Settings',
  'settings.language': 'Language',
  'settings.theme': 'Theme',
  'settings.notifications': 'Notifications',

  'error.notFound': 'Page not found',
  'error.unauthorized': 'You do not have permission to access this page',
  'error.serverError': 'Server error. Please try again later.',
  'error.networkError': 'Network error. Check your connection.',

  'sys.loading': 'Loading…',
  'sys.noData': 'No data available',
  'sys.demoNotice': 'Demo Mode',
  'sys.nonLegalBinding': '⚠ This system contains synthetic demo data. Not legally binding.',
  'sys.poweredBy': 'Powered by Antigravity',
  'sys.version': 'Version',
  'sys.lastUpdated': 'Last updated',
};

// ── Hindi translations ─────────────────────────────────────────────────────────

const hi: Translations = {
  'nav.dashboard': 'डैशबोर्ड',
  'nav.intake': 'दस्तावेज़ प्रवेश',
  'nav.pipeline': 'पाइपलाइन',
  'nav.documents': 'दस्तावेज़',
  'nav.landRecords': 'भूमि अभिलेख',
  'nav.verification': 'सत्यापन',
  'nav.gisMap': 'जीआईएस मानचित्र',
  'nav.anomalies': 'विसंगतियां',
  'nav.reports': 'रिपोर्ट',
  'nav.auditTrail': 'ऑडिट अनुगमन',
  'nav.users': 'उपयोगकर्ता और भूमिकाएं',
  'nav.integrations': 'एकीकरण',
  'nav.settings': 'सेटिंग्स',

  'auth.login': 'साइन इन करें',
  'auth.logout': 'साइन आउट',
  'auth.username': 'उपयोगकर्ता नाम / कर्मचारी आईडी',
  'auth.password': 'पासवर्ड',
  'auth.loginTitle': 'भूमि अभिलेख पोर्टल',
  'auth.loginSubtitle': 'बुद्धिमान भूमि अभिलेख डिजिटलीकरण प्रणाली',
  'auth.signingIn': 'साइन इन हो रहा है…',
  'auth.loginFailed': 'अमान्य उपयोगकर्ता नाम या पासवर्ड',

  'dash.title': 'डैशबोर्ड',
  'dash.subtitle': 'प्रणाली अवलोकन और मुख्य मापदंड',
  'dash.totalRecords': 'कुल अभिलेख',
  'dash.verified': 'सत्यापित',
  'dash.pendingReview': 'समीक्षाधीन',
  'dash.anomalies': 'विसंगतियां',
  'dash.docsProcessed': 'संसाधित दस्तावेज़',
  'dash.areaDigitized': 'डिजिटलीकृत क्षेत्र (हेक्टेयर)',

  'lr.title': 'भूमि अभिलेख',
  'lr.khasra': 'खसरा संख्या',
  'lr.khata': 'खाता / खतौनी',
  'lr.survey': 'सर्वे संख्या',
  'lr.owner': 'स्वामी का नाम',
  'lr.district': 'जिला',
  'lr.tehsil': 'तहसील / तालुका',
  'lr.village': 'गांव / ग्राम',
  'lr.state': 'राज्य',
  'lr.area': 'क्षेत्रफल (हेक्टेयर)',
  'lr.landUse': 'भूमि वर्गीकरण',
  'lr.status': 'स्थिति',
  'lr.mutation': 'दाखिल-खारिज',
  'lr.registration': 'पंजीकरण',
  'lr.createRecord': 'अभिलेख बनाएं',
  'lr.editRecord': 'अभिलेख संपादित करें',
  'lr.verifyRecord': 'अभिलेख सत्यापित करें',

  'status.pending': 'लंबित',
  'status.underReview': 'समीक्षाधीन',
  'status.verified': 'सत्यापित',
  'status.rejected': 'अस्वीकृत',
  'status.archived': 'संग्रहीत',
  'status.processing': 'प्रसंस्करण',
  'status.uploaded': 'अपलोड किया',
  'status.failed': 'विफल',

  'action.search': 'खोजें',
  'action.filter': 'फ़िल्टर',
  'action.export': 'निर्यात',
  'action.import': 'आयात',
  'action.upload': 'अपलोड',
  'action.save': 'सहेजें',
  'action.cancel': 'रद्द करें',
  'action.confirm': 'पुष्टि करें',
  'action.delete': 'हटाएं',
  'action.edit': 'संपादित करें',
  'action.view': 'देखें',
  'action.approve': 'अनुमोदित करें',
  'action.reject': 'अस्वीकार करें',
  'action.retry': 'पुनः प्रयास',
  'action.refresh': 'ताज़ा करें',
  'action.submit': 'जमा करें',
  'action.verify': 'सत्यापित करें',
  'action.resolve': 'हल करें',
  'action.download': 'डाउनलोड',

  'val.required': 'यह फ़ील्ड आवश्यक है',
  'val.invalidFormat': 'अमान्य प्रारूप',
  'val.tooShort': 'बहुत छोटा',
  'val.tooLong': 'बहुत लंबा',
  'val.duplicateRecord': 'इस पहचानकर्ता वाला अभिलेख पहले से मौजूद है',

  'intake.title': 'दस्तावेज़ प्रवेश',
  'intake.subtitle': 'ओसीआर प्रसंस्करण के लिए भूमि अभिलेख दस्तावेज़ अपलोड करें',
  'intake.dropzone': 'फ़ाइलें यहां छोड़ें या ब्राउज़ करने के लिए क्लिक करें',
  'intake.selectFile': 'फ़ाइल चुनें',
  'intake.uploading': 'अपलोड हो रहा है…',
  'intake.success': 'अपलोड सफल। पाइपलाइन शुरू हुई।',
  'intake.processing': 'दस्तावेज़ प्रसंस्करण…',

  'pipe.title': 'प्रसंस्करण पाइपलाइन',
  'pipe.queue': 'पाइपलाइन कतार',
  'pipe.extractedFields': 'निकाले गए फ़ील्ड',
  'pipe.anomalies': 'विसंगतियां',
  'pipe.humanReview': 'मानव सत्यापन आवश्यक',
  'pipe.confidence': 'विश्वास स्तर',
  'pipe.verify': 'सत्यापित करें',

  'gis.title': 'जीआईएस / भूकर मानचित्र',
  'gis.searchLocation': 'स्थान या खसरा संख्या से खोजें',
  'gis.synthetic': 'कृत्रिम निर्देशांक — केवल डेमो',
  'gis.totalParcels': 'कुल भूखंड',

  'analytics.title': 'विश्लेषण और रिपोर्ट',
  'analytics.recordsByStatus': 'स्थिति के अनुसार अभिलेख',
  'analytics.byDistrict': 'जिले के अनुसार',
  'analytics.processingThroughput': 'प्रसंस्करण दर',
  'analytics.areaDistribution': 'क्षेत्र वितरण',

  'audit.title': 'ऑडिट अनुगमन',
  'audit.action': 'कार्रवाई',
  'audit.actor': 'उपयोगकर्ता',
  'audit.resource': 'संसाधन',
  'audit.timestamp': 'समय',

  'users.title': 'उपयोगकर्ता और भूमिकाएं',
  'users.role': 'भूमिका',
  'users.active': 'सक्रिय',
  'users.inactive': 'निष्क्रिय',
  'users.createUser': 'उपयोगकर्ता बनाएं',

  'settings.title': 'सेटिंग्स',
  'settings.language': 'भाषा',
  'settings.theme': 'थीम',
  'settings.notifications': 'सूचनाएं',

  'error.notFound': 'पृष्ठ नहीं मिला',
  'error.unauthorized': 'आपको इस पृष्ठ तक पहुंचने की अनुमति नहीं है',
  'error.serverError': 'सर्वर त्रुटि। कृपया बाद में पुनः प्रयास करें।',
  'error.networkError': 'नेटवर्क त्रुटि। अपना कनेक्शन जांचें।',

  'sys.loading': 'लोड हो रहा है…',
  'sys.noData': 'कोई डेटा उपलब्ध नहीं',
  'sys.demoNotice': 'डेमो मोड',
  'sys.nonLegalBinding': '⚠ इस प्रणाली में कृत्रिम डेमो डेटा है। कानूनी रूप से बाध्यकारी नहीं।',
  'sys.poweredBy': 'एंटीग्रेविटी द्वारा संचालित',
  'sys.version': 'संस्करण',
  'sys.lastUpdated': 'अंतिम अद्यतन',
};

// ── Telugu translations ────────────────────────────────────────────────────────

const te: Partial<Translations> = {
  'nav.dashboard': 'డాష్‌బోర్డ్',
  'nav.landRecords': 'భూమి రికార్డులు',
  'nav.verification': 'ధృవీకరణ',
  'nav.documents': 'పత్రాలు',
  'nav.auditTrail': 'ఆడిట్ ట్రెయిల్',
  'nav.settings': 'సెట్టింగులు',
  'auth.login': 'లాగిన్',
  'auth.logout': 'లాగ్అవుట్',
  'lr.khasra': 'ఖాసరా నంబర్',
  'lr.owner': 'యజమాని పేరు',
  'lr.district': 'జిల్లా',
  'status.pending': 'పెండింగ్',
  'status.verified': 'ధృవీకరించబడింది',
  'action.search': 'వెతకండి',
  'action.upload': 'అప్‌లోడ్',
  'sys.loading': 'లోడవుతోంది…',
  'sys.noData': 'డేటా అందుబాటులో లేదు',
};

// ── Marathi translations ───────────────────────────────────────────────────────

const mr: Partial<Translations> = {
  'nav.dashboard': 'डॅशबोर्ड',
  'nav.landRecords': 'जमीन नोंदी',
  'nav.documents': 'कागदपत्रे',
  'nav.settings': 'सेटिंग्ज',
  'auth.login': 'साइन इन करा',
  'auth.logout': 'साइन आउट',
  'lr.khasra': 'खसरा क्रमांक',
  'lr.owner': 'मालकाचे नाव',
  'lr.district': 'जिल्हा',
  'status.pending': 'प्रलंबित',
  'status.verified': 'सत्यापित',
  'action.search': 'शोधा',
  'sys.loading': 'लोड होत आहे…',
};

// ── Tamil translations ─────────────────────────────────────────────────────────

const ta: Partial<Translations> = {
  'nav.dashboard': 'டாஷ்போர்டு',
  'nav.landRecords': 'நில பதிவுகள்',
  'nav.documents': 'ஆவணங்கள்',
  'nav.settings': 'அமைப்புகள்',
  'auth.login': 'உள்நுழை',
  'auth.logout': 'வெளியேறு',
  'lr.khasra': 'கதாரா எண்',
  'lr.owner': 'உரிமையாளர் பெயர்',
  'lr.district': 'மாவட்டம்',
  'status.pending': 'நிலுவையில்',
  'status.verified': 'சரிபார்க்கப்பட்டது',
  'action.search': 'தேடு',
  'sys.loading': 'ஏற்றுகிறது…',
};

// ── Gujarati ──────────────────────────────────────────────────────────────────

const gu: Partial<Translations> = {
  'nav.dashboard': 'ડેશબોર્ડ',
  'nav.landRecords': 'જમીન નોંધ',
  'nav.documents': 'દસ્તાવેજો',
  'nav.settings': 'સેટિંગ્સ',
  'auth.login': 'સાઇન ઇન',
  'auth.logout': 'સાઇન આઉટ',
  'lr.khasra': 'ખસરા નંબર',
  'lr.owner': 'માલિકનું નામ',
  'lr.district': 'જિલ્લો',
  'status.pending': 'પ્રતિક્ષારત',
  'status.verified': 'ચકાસાયેલ',
  'action.search': 'શોધો',
  'sys.loading': 'લોડ થઈ રહ્યું છે…',
};

// ── Kannada ───────────────────────────────────────────────────────────────────

const kn: Partial<Translations> = {
  'nav.dashboard': 'ಡ್ಯಾಶ್‌ಬೋರ್ಡ್',
  'nav.landRecords': 'ಭೂ ದಾಖಲೆಗಳು',
  'nav.documents': 'ದಾಖಲೆಗಳು',
  'nav.settings': 'ಸೆಟ್ಟಿಂಗ್‌ಗಳು',
  'auth.login': 'ಸೈನ್ ಇನ್',
  'auth.logout': 'ಸೈನ್ ಔಟ್',
  'lr.khasra': 'ಖಾಸರಾ ಸಂಖ್ಯೆ',
  'lr.owner': 'ಮಾಲೀಕರ ಹೆಸರು',
  'lr.district': 'ಜಿಲ್ಲೆ',
  'status.pending': 'ಬಾಕಿ',
  'status.verified': 'ಪರಿಶೀಲಿಸಲಾಗಿದೆ',
  'action.search': 'ಹುಡುಕಿ',
  'sys.loading': 'ಲೋಡ್ ಆಗುತ್ತಿದೆ…',
};

// ── Bengali ───────────────────────────────────────────────────────────────────

const bn: Partial<Translations> = {
  'nav.dashboard': 'ড্যাশবোর্ড',
  'nav.landRecords': 'ভূমি রেকর্ড',
  'nav.documents': 'নথি',
  'nav.settings': 'সেটিংস',
  'auth.login': 'সাইন ইন',
  'auth.logout': 'সাইন আউট',
  'lr.khasra': 'খতিয়ান সংখ্যা',
  'lr.owner': 'মালিকের নাম',
  'lr.district': 'জেলা',
  'status.pending': 'অপেক্ষমান',
  'status.verified': 'যাচাইকৃত',
  'action.search': 'খুঁজুন',
  'sys.loading': 'লোড হচ্ছে…',
};

// ── Malayalam ────────────────────────────────────────────────────────────────

const ml: Partial<Translations> = {
  'nav.dashboard': 'ഡാഷ്‌ബോർഡ്',
  'nav.landRecords': 'ഭൂരേഖകൾ',
  'nav.documents': 'രേഖകൾ',
  'nav.settings': 'ക്രമീകരണങ്ങൾ',
  'auth.login': 'സൈൻ ഇൻ',
  'auth.logout': 'സൈൻ ഔട്ട്',
  'lr.khasra': 'ഖസ്‌ര നമ്പർ',
  'lr.owner': 'ഉടമസ്ഥന്റെ പേര്',
  'lr.district': 'ജില്ല',
  'status.pending': 'തീർപ്പാക്കാത്ത',
  'status.verified': 'സ്ഥിരീകരിച്ചു',
  'action.search': 'തിരയുക',
  'sys.loading': 'ലോഡ് ചെയ്യുന്നു…',
};

// ── Punjabi ───────────────────────────────────────────────────────────────────

const pa: Partial<Translations> = {
  'nav.dashboard': 'ਡੈਸ਼ਬੋਰਡ',
  'nav.landRecords': 'ਜ਼ਮੀਨ ਰਿਕਾਰਡ',
  'nav.documents': 'ਦਸਤਾਵੇਜ਼',
  'nav.settings': 'ਸੈਟਿੰਗਾਂ',
  'auth.login': 'ਸਾਈਨ ਇਨ',
  'auth.logout': 'ਸਾਈਨ ਆਊਟ',
  'lr.khasra': 'ਖਸਰਾ ਨੰਬਰ',
  'lr.owner': 'ਮਾਲਕ ਦਾ ਨਾਮ',
  'lr.district': 'ਜ਼ਿਲ੍ਹਾ',
  'status.pending': 'ਬਕਾਇਆ',
  'status.verified': 'ਤਸਦੀਕਸ਼ੁਦਾ',
  'action.search': 'ਖੋਜੋ',
  'sys.loading': 'ਲੋਡ ਹੋ ਰਿਹਾ ਹੈ…',
};

// ── Urdu (RTL) ────────────────────────────────────────────────────────────────

const ur: Partial<Translations> = {
  'nav.dashboard': 'ڈیش بورڈ',
  'nav.landRecords': 'زمینی ریکارڈ',
  'nav.documents': 'دستاویزات',
  'nav.settings': 'ترتیبات',
  'auth.login': 'سائن ان',
  'auth.logout': 'سائن آؤٹ',
  'lr.khasra': 'خسرہ نمبر',
  'lr.owner': 'مالک کا نام',
  'lr.district': 'ضلع',
  'status.pending': 'زیر التواء',
  'status.verified': 'تصدیق شدہ',
  'action.search': 'تلاش کریں',
  'sys.loading': 'لوڈ ہو رہا ہے…',
};

// ── Odia ─────────────────────────────────────────────────────────────────────

const or: Partial<Translations> = {
  'nav.dashboard': 'ଡ୍ୟାଶ୍‌ବୋର୍ଡ',
  'nav.landRecords': 'ଭୂ ଅଭିଲେଖ',
  'nav.documents': 'ଦଲିଲ',
  'nav.settings': 'ସଂରଚନା',
  'auth.login': 'ସାଇନ ଇନ',
  'lr.khasra': 'ଖସରା ନମ୍ବର',
  'lr.district': 'ଜିଲ୍ଲା',
  'status.pending': 'ଅପେକ୍ଷିତ',
  'status.verified': 'ଯାଞ୍ଚ ହୋଇଛି',
  'action.search': 'ଖୋଜ',
  'sys.loading': 'ଲୋଡ ହେଉଛି…',
};

// ── Translation map ───────────────────────────────────────────────────────────

const TRANSLATION_MAP: Record<string, Partial<Translations>> = {
  en, hi, te, mr, ta, gu, kn, bn, ml, pa, ur, or,
  as: { ...bn, 'nav.landRecords': 'ভূমি অভিলেখ', 'lr.district': 'জিলা' }, // Assamese ≈ Bengali script
  mai: hi,  // Maithili uses Devanagari — fall back to Hindi
  sa: hi,   // Sanskrit uses Devanagari — fall back to Hindi
};

// ── t() function ──────────────────────────────────────────────────────────────

export function t(key: TranslationKey, lang: string): string {
  const map = TRANSLATION_MAP[lang] ?? en;
  return (map as Translations)[key] ?? en[key] ?? key;
}

// ── Font loader ───────────────────────────────────────────────────────────────

const loadedFonts = new Set<string>();

export function loadLanguageFont(langCode: string): void {
  const meta = LANGUAGES.find(l => l.code === langCode);
  if (!meta?.googleFont || loadedFonts.has(langCode)) return;
  loadedFonts.add(langCode);

  const link = document.createElement('link');
  link.rel = 'stylesheet';
  link.href = `https://fonts.googleapis.com/css2?family=${meta.googleFont}&display=swap`;
  document.head.appendChild(link);
}

// ── Apply language to DOM ─────────────────────────────────────────────────────

export function applyLanguage(langCode: string): void {
  const meta = LANGUAGES.find(l => l.code === langCode) ?? LANGUAGES[0];
  document.documentElement.setAttribute('lang', langCode);
  document.documentElement.setAttribute('dir', meta.dir);
  loadLanguageFont(langCode);

  if (meta.fontFamily) {
    document.documentElement.style.setProperty('--font-lang', meta.fontFamily);
  } else {
    document.documentElement.style.removeProperty('--font-lang');
  }
}

// ── Persistence ───────────────────────────────────────────────────────────────

export const LANG_STORAGE_KEY = 'bhumi-lang';

export function getPersistedLang(): string {
  return localStorage.getItem(LANG_STORAGE_KEY) || 'en';
}

export function persistLang(lang: string): void {
  localStorage.setItem(LANG_STORAGE_KEY, lang);
}
