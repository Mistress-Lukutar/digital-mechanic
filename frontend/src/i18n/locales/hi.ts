import type { Messages } from '../index'

const hi = {
  'app.title': 'डिजिटल मैकेनिक',
  'app.nav.garage': 'गैराज',
  'app.nav.chat': 'चैट',
  'app.nav.fleet': 'फ़्लीट',
  'app.nav.admin': 'एडमिन',
  'app.role.admin': 'एडमिन',
  'app.role.user': 'उपयोगकर्ता',
  'app.logout': 'लॉगआउट',
  'app.stub.title': '«{page}» खंड',
  'app.stub.body': 'अगले चरण में उपलब्ध होगा।',
  'login.username': 'उपयोगकर्ता नाम',
  'login.password': 'पासवर्ड',
  'login.placeholder.username': 'नाम दर्ज करें',
  'login.placeholder.password': 'पासवर्ड दर्ज करें',
  'login.submit': 'लॉगिन',
  'login.submitting': 'लॉगिन…',
  'login.change.title': 'पासवर्ड बदलें',
  'login.change.hint': 'जारी रखने के लिए नया पासवर्ड सेट करें।',
  'login.change.old': 'पुराना पासवर्ड',
  'login.change.new': 'नया पासवर्ड',
  'login.change.new.min': 'कम से कम 8 अक्षर',
  'login.change.repeat': 'नया पासवर्ड दोबारा दर्ज करें',
  'login.change.save': 'पासवर्ड सहेजें',
  'login.change.saving': 'सहेजा जा रहा है…',
  'login.error.fillAll': 'सभी फ़ील्ड भरें',
  'login.error.min8': 'नया पासवर्ड: कम से कम 8 अक्षर',
  'login.error.mismatch': 'पासवर्ड मेल नहीं खाते',
  'login.error.password': 'लॉगिन त्रुटि',
  'login.error.change': 'पासवर्ड बदलने में त्रुटि',
  'login.consent': 'डेमो सिस्टम में डेटा प्रोसेसिंग के लिए सहमत (डेटा सिंथेटिक, 152-FZ)',

  // ---------------------------------------------------------------------------
  // garage.* — GarageView
  // ---------------------------------------------------------------------------
  'garage.search.placeholder': 'वाहन नंबर, गैराज नंबर, ब्रांड, मॉडल…',
  'garage.filter.all': 'सभी',
  'garage.filter.normal': 'सामान्य',
  'garage.filter.attention': 'ध्यान चाहिए',
  'garage.filter.quarantine': 'कारांटीन',
  'garage.empty': 'कुछ नहीं मिला',
  'garage.counts_anomalies': 'विचलन: {n}',
  'garage.counts_checks': 'जाँच: {m}',

  // ---------------------------------------------------------------------------
  // status.* — StatusCard
  // ---------------------------------------------------------------------------
  'status.label.normal': 'सामान्य',
  'status.label.anomaly': 'विचलन',
  'status.label.check_failed': 'रिकॉर्डिंग विफल',
  'status.score.label': 'स्कोर',
  'status.confidence.label': 'कॉन्फिडेंस',
  'status.signal.label': 'सिग्नल गुणवत्ता:',
  'status.signal.good': 'भरोसेमंद रिकॉर्ड',
  'status.signal.warning': 'रुकावट',
  'status.signal.bad': 'रिकॉर्ड अनुपयोगी',
  'status.check_failed_warning': 'रिकॉर्ड अनुपयोगी — निदान नहीं लगाया जाएगा, रिकॉर्ड दोहराएँ',

  // ---------------------------------------------------------------------------
  // history.* — HistoryPanel
  // ---------------------------------------------------------------------------
  'history.title': 'वाहन इतिहास',
  'history.checks_section': 'जाँच',
  'history.tickets_section': 'टिकट',
  'history.no_checks': 'अभी तक कोई जाँच नहीं',
  'history.no_tickets': 'कोई टिकट नहीं',
  'history.urgency.high': 'उच्च',
  'history.urgency.medium': 'मध्यम',
  'history.urgency.low': 'निम्न',
  'history.trend_worsening': 'Score पिछली {n} जाँचों में बढ़ रहा है — स्थिति खराब हो रही है',
  'history.trend_improving': 'Score पिछली {n} जाँचों में कम हो रहा है — स्थिति सुधर रही है',
  'history.trend_stable': 'Score स्थिर है — खराब होने के संकेत नहीं',

  // ---------------------------------------------------------------------------
  // chart.* — AnomalyChart
  // ---------------------------------------------------------------------------
  'chart.title': 'anomaly_score हाल की जाँचों के अनुसार',
  'chart.no_data': 'ग्राफ़ के लिए पर्याप्त डेटा नहीं',
  // ---------------------------------------------------------------------------
  // chat.* — ChatView
  // ---------------------------------------------------------------------------
  'chat.back': 'वापस',
  'chat.new_dialog': 'नया संवाद',
  'chat.history': 'इतिहास',
  'chat.document': 'दस्तावेज़',
  'chat.select_doc': 'चैट से दस्तावेज़ चुनें',
  'chat.streaming': 'AI टाइप कर रहा है...',
  'chat.input.placeholder': 'संदेश दर्ज करें...',
  'chat.stop': 'रोकें',
  'chat.quick.diagnostic.label': 'निदान प्राप्त करें',
  'chat.quick.diagnostic.text': 'निदान परिणाम प्राप्त करें',
  'chat.quick.can_move.label': 'बेस तक चलाया जा सकता है?',
  'chat.quick.can_move.text': 'गाड़ी को अपनी शक्ति से बेस पर ले जाया जा सकता है?',
  'chat.quick.ticket.label': 'टिकट बनाएँ',
  'chat.quick.ticket.text': 'खराबी के लिए टिकट बनाएँ',
  'chat.error.connection': 'कनेक्शन त्रुटि',
  'chat.mic.label': 'वॉइस इनपुट',
  'chat.mic.listening': 'सुन रहा हूँ…',
  'chat.empty_vehicle': 'फ़्लीट से अनुरोध चुनें या इतिहास से चैट खोलें',
  'chat.reasoning.toggle': 'सोच रहा हूँ…',
  'chat.attach.label': 'छवि संलग्न करें',
  'chat.attach.remove': 'छवि हटाएँ',

  // ---------------------------------------------------------------------------
  // chats.* — ChatsPanel
  // ---------------------------------------------------------------------------
  'chats.tab': 'चैट',
  'chats.empty': 'अभी कोई चैट नहीं है',
  'chats.untitled': 'बिना शीर्षक',
  'chats.loading': 'लोड हो रहा है…',
  'chats.delete': 'चैट हटाएँ',
  'chats.delete_confirm': 'इस चैट को हटाएँ? संदेश इतिहास खो जाएगा।',

  // ---------------------------------------------------------------------------
  // tools.* — AgentStep tool-name display map
  // ---------------------------------------------------------------------------
  'tools.get_diagnostic_result': 'निदान',
  'tools.get_vehicle_info': 'वाहन जानकारी',
  'tools.search_rag': 'डेटाबेस में खोजें',
  'tools.create_ticket': 'टिकट बनाना',
  'tools.check_signal_quality': 'सिग्नल गुणवत्ता',
  'tools.analyze_signals': 'सिग्नल विश्लेषण',

  // ---------------------------------------------------------------------------
  // ticket.* — TicketForm
  // ---------------------------------------------------------------------------
  'ticket.conclusion.label': 'निष्कर्ष',
  'ticket.conclusion.placeholder': 'निष्कर्ष का वर्णन करें...',
  'ticket.urgency.label': 'प्राथमिकता',
  'ticket.urgency.low': 'निम्न',
  'ticket.urgency.medium': 'मध्यम',
  'ticket.urgency.high': 'उच्च',
  'ticket.ops.label': 'ऑपरेशन (प्रति पंक्ति एक)',
  'ticket.ops.placeholder': 'तेल बदलना\nबेल्ट जाँच',
  'ticket.parts.label': 'पार्ट्स (वैकल्पिक, प्रति पंक्ति एक)',
  'ticket.parts.placeholder': 'ऑयल फ़िल्टर, एयर फ़िल्टर',
  'ticket.refs.label': 'मैन्युअल संदर्भ',
  'ticket.ref.manual_placeholder': 'मैन्युअल का नाम',
  'ticket.ref.page_placeholder': 'पृ.',
  'ticket.ref.remove_title': 'हटाएँ',
  'ticket.ref.add': '+ संदर्भ जोड़ें',
  'ticket.submit': 'TOiR को भेजें',
  'ticket.submitting': 'भेजा जा रहा है…',
  'ticket.cancel': 'रद्द करें',
  'ticket.success': 'टिकट {id} बनाया गया',
  'ticket.close': 'बंद करें',
  'ticket.validation.conclusion': 'निष्कर्ष दर्ज करें',
  'ticket.validation.ops': 'कम से कम एक ऑपरेशन बताएँ',
  'ticket.validation.ref_manual': 'संदर्भ #{n}: मैन्युअल बताएँ',
  'ticket.validation.ref_page': 'संदर्भ #{n}: पृष्ठ संख्या ≥ 1 होनी चाहिए',
  'ticket.error.create': 'टिकट बनाने में त्रुटि',

  // ---------------------------------------------------------------------------
  // doc.* — DocPanel
  // ---------------------------------------------------------------------------
  'doc.page.title': 'पृ. {n}/{m}',
  'doc.loading': 'लोड हो रहा है…',
  'doc.error.unavailable': 'PDF फ़ाइल सर्वर पर उपलब्ध नहीं है',
  'doc.error.generic': 'त्रुटि: {msg}',
  'doc.prev_page': 'पिछला पृष्ठ',
  'doc.next_page': 'अगला पृष्ठ',
  'doc.zoom_in': 'ज़ूम इन करें',
  'doc.zoom_out': 'ज़ूम आउट करें',

  // ---------------------------------------------------------------------------
  // fleet.* — FleetView
  // ---------------------------------------------------------------------------
  'fleet.group.normal': 'सामान्य',
  'fleet.group.attention': 'ध्यान',
  'fleet.group.quarantine': 'कारांटीन',
  'fleet.requires_attention': 'ध्यान चाहिए',
  'fleet.priority_list': 'प्राथमिकता सूची',
  'fleet.no_anomalies': 'विचलन रहित',
  'fleet.open': 'खोलें',
  'fleet.retry': 'पुनः प्रयास',
  'fleet.all_fleet': 'सभी फ़्लीट ({n})',
  'fleet.table.garage_no': 'गैराज नंबर',
  'fleet.table.vehicle_id': 'ID वाहन',
  'fleet.table.make_model': 'मार्क / मॉडल',
  'fleet.table.engine': 'इंजन',
  'fleet.table.group': 'समूह',
  'fleet.table.status': 'स्थिति',

  // ---------------------------------------------------------------------------
  // admin.* — AdminView
  // ---------------------------------------------------------------------------
  'admin.tab.dashboard': 'डैशबोर्ड',
  'admin.tab.users': 'उपयोगकर्ता',
  'admin.tab.llm': 'LLM सेटिंग्स',
  'admin.dashboard.title': 'उपयोग डैशबोर्ड',
  'admin.stat.requests': 'अनुरोध',
  'admin.stat.errors': 'त्रुटियाँ',
  'admin.stat.input_tokens': 'इनपुट टोकन',
  'admin.stat.output_tokens': 'आउटपुट टोकन',
  'admin.recent_requests': 'हाल के अनुरोध',
  'admin.refresh': 'रिफ़्रेश',
  'admin.loading': 'लोड हो रहा है…',
  'admin.table.time': 'समय',
  'admin.table.user': 'उपयोगकर्ता',
  'admin.table.kind': 'प्रकार',
  'admin.table.model': 'मॉडल',
  'admin.table.vehicle_id': 'ID वाहन',
  'admin.table.input_tokens': 'इनपुट टोकन',
  'admin.table.output_tokens': 'आउटपुट टोकन',
  'admin.table.duration': 'अवधि (ms)',
  'admin.table.status': 'स्थिति',
  'admin.error_label': 'त्रुटि',
  'admin.no_records': 'कोई रिकॉर्ड नहीं',
  'admin.users.title': 'उपयोगकर्ता',
  'admin.add_user': 'उपयोगकर्ता जोड़ें',
  'admin.username_placeholder': 'उपयोगकर्ता नाम',
  'admin.password_placeholder': 'पासवर्ड (न्यूनतम 8)',
  'admin.create': 'बनाएँ',
  'admin.table.name': 'नाम',
  'admin.table.role': 'भूमिका',
  'admin.table.change_password': 'पासवर्ड बदलें',
  'admin.table.created_at': 'बनाने की तारीख',
  'admin.table.actions': 'क्रियाएँ',
  'admin.must_change_pw': 'पासवर्ड बदलेगा',
  'admin.new_password_placeholder': 'नया पासवर्ड',
  'admin.reset_password': 'पासवर्ड रीसेट',
  'admin.delete': 'हटाएँ',
  'admin.no_users': 'कोई उपयोगकर्ता नहीं',
  'admin.loading_indicator': '…',
  'admin.settings.title': 'LLM सेटिंग्स',
  'admin.protocol_label': 'प्रोटोकॉल',
  'admin.base_url_label': 'Base URL',
  'admin.api_key_label': 'API कुंजी',
  'admin.not_set': 'निर्धारित नहीं',
  'admin.api_key_hint': 'कुंजी सर्वर पर संग्रहीत होती है और खुले रूप में वापस नहीं आती',
  'admin.model_label': 'मॉडल',
  'admin.temperature_label': 'Temperature (0–1)',
  'admin.max_output_tokens_label': 'Max output tokens',
  'admin.empty_no_limit': 'खाली = बिना सीमा',
  'admin.save': 'सहेजें',
  'admin.saving': 'सहेजा जा रहा है…',
  'admin.current_settings': 'वर्तमान सेटिंग्स',
  'admin.delete_user_title': 'उपयोगकर्ता हटाएँ',
  'admin.delete_user_message': '«{username}» हटाएँ?',
  'admin.password_min_8': 'पासवर्ड में कम से कम 8 अक्षर होने चाहिए',
  'admin.detail_question': 'प्रश्न',
  'admin.detail_answer': 'उत्तर',
  'admin.detail_tools': 'उपकरण',
  'admin.detail_citations': 'उद्धरण',
  'admin.detail_ticket_draft': 'टिकट ड्राफ्ट',
  'admin.detail_image': 'छवि के साथ',
  'admin.detail_hint': '"chat" पंक्ति पर क्लिक — प्रश्न, उत्तर और उद्धरण',
  'admin.detail_loading': 'लोड हो रहा है…',
  'admin.detail_error': 'विवरण अनुपलब्ध',

  // ---------------------------------------------------------------------------
  // confirm.* — useConfirm defaults
  // ---------------------------------------------------------------------------
  'confirm.ok': 'पुष्टि करें',
  'confirm.cancel': 'रद्द करें',

  // ---------------------------------------------------------------------------
  // config.* — config-status warning banner
  // ---------------------------------------------------------------------------
  'config.warning_title': 'सिस्टम कॉन्फ़िगरेशन में समस्याएँ',
  'config.dismiss': 'छिपाएँ',
} satisfies Messages

export default hi
