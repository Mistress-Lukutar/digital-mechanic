import type { Messages } from '../index'

const uz = {
  'app.title': 'Raqamli mexanik',
  'app.nav.garage': 'Garaj',
  'app.nav.chat': 'Chat',
  'app.nav.fleet': 'Park',
  'app.nav.admin': 'Admin',
  'app.role.admin': 'admin',
  'app.role.user': 'foydalanuvchi',
  'app.logout': 'Chiqish',
  'app.stub.title': '«{page}» boʻlimi',
  'app.stub.body': 'Keyingi bosqichda paydo boʻladi.',
  'login.username': 'Foydalanuvchi nomi',
  'login.password': 'Parol',
  'login.placeholder.username': 'Ismni kiriting',
  'login.placeholder.password': 'Parolni kiriting',
  'login.submit': 'Kirish',
  'login.submitting': 'Kirish…',
  'login.change.title': 'Parolni oʻzgartiring',
  'login.change.hint': 'Davom etish uchun yangi parol oʻrnating.',
  'login.change.old': 'Eski parol',
  'login.change.new': 'Yangi parol',
  'login.change.new.min': 'Minimal 8 ta belgi',
  'login.change.repeat': 'Yangi parolni takrorlang',
  'login.change.save': 'Parolni saqlash',
  'login.change.saving': 'Saqlanmoqda…',
  'login.error.fillAll': 'Barcha maydonlarni toʻldiring',
  'login.error.min8': 'Yangi parol: minimal 8 ta belgi',
  'login.error.mismatch': 'Parollar mos kelmaydi',
  'login.error.password': 'Kirish xatosi',
  'login.error.change': 'Parolni oʻzgartirish xatosi',
  'login.adminHint': 'Boshlangʻich admin paroli birinchi ishga tushirishda server konsoliga chiqariladi.',
  'login.consent': 'Demo tizimida maʼlumotlarni qayta ishlashga roziman (maʼlumotlar sintetik, 152-FZ)',

  // ---------------------------------------------------------------------------
  // garage.* — GarageView
  // ---------------------------------------------------------------------------
  'garage.search.placeholder': 'Davlat raqami, garaj №, marka, model…',
  'garage.filter.all': 'Barchasi',
  'garage.filter.normal': 'Normal',
  'garage.filter.attention': 'Eʼtibor kerak',
  'garage.filter.quarantine': 'Karantin',
  'garage.empty': 'Hech narsa topilmadi',
  'garage.counts_anomalies': 'Anomaliyalar: {n}',
  'garage.counts_checks': 'Tekshiruvlar: {m}',

  // ---------------------------------------------------------------------------
  // status.* — StatusCard
  // ---------------------------------------------------------------------------
  'status.label.normal': 'Normal',
  'status.label.anomaly': 'Anomaliya',
  'status.label.check_failed': 'Yozuvda xatolik',
  'status.score.label': 'Baho',
  'status.confidence.label': 'Ishonchlilik',
  'status.signal.label': 'Signal sifati:',
  'status.signal.good': 'Ishonchli yozuv',
  'status.signal.warning': 'Shovqin',
  'status.signal.bad': 'Yozuv yaroqsiz',
  'status.check_failed_warning': 'Yozuv yaroqsiz — diagnostika qoʻyilmaydi, yozuvni takrorlang',

  // ---------------------------------------------------------------------------
  // history.* — HistoryPanel
  // ---------------------------------------------------------------------------
  'history.title': 'Transport tarixi',
  'history.checks_section': 'Tekshiruvlar',
  'history.tickets_section': 'Arizalar',
  'history.no_checks': 'Tekshiruvlar hali boʻlmagan',
  'history.no_tickets': 'Arizalar yoʻq',
  'history.urgency.high': 'Yuqori',
  'history.urgency.medium': 'Oʻrtacha',
  'history.urgency.low': 'Past',

  // ---------------------------------------------------------------------------
  // chart.* — AnomalyChart
  // ---------------------------------------------------------------------------
  'chart.title': 'anomaly_score soʻnggi tekshiruvlar boʻyicha',
  'chart.no_data': 'Grafik uchun maʼlumot yetarli emas',
  'chart.caption': 'Tarix koʻrsatiladi; bashorat qilinmaydi.',

  // ---------------------------------------------------------------------------
  // chat.* — ChatView
  // ---------------------------------------------------------------------------
  'chat.back': 'Orqaga',
  'chat.new_dialog': 'Yangi suhbat',
  'chat.history': 'Tarix',
  'chat.document': 'Hujjat',
  'chat.select_doc': 'Chatdan hujjat tanlang',
  'chat.streaming': 'Sunʼiy intellekt yozmoqda...',
  'chat.input.placeholder': 'Xabar kiriting...',
  'chat.stop': 'Toʻxtatish',
  'chat.quick.diagnostic.label': 'Diagnostika olish',
  'chat.quick.diagnostic.text': 'Diagnostika natijasini olish',
  'chat.quick.can_move.label': 'Koʻchirish mumkinmi?',
  'chat.quick.can_move.text': 'Avtomobilni oʻz kuchi bilan bazaga koʻchirish mumkinmi?',
  'chat.quick.ticket.label': 'Ariza yaratish',
  'chat.quick.ticket.text': 'Nuqson haqida ariza yarating',
  'chat.error.connection': 'Ulanish xatosi',

  // ---------------------------------------------------------------------------
  // tools.* — AgentStep tool-name display map
  // ---------------------------------------------------------------------------
  'tools.get_diagnostic_result': 'Diagnostika',
  'tools.get_vehicle_info': 'Transport maʼlumotlari',
  'tools.search_rag': 'Bazada qidirish',
  'tools.create_ticket': 'Ariza yaratish',
  'tools.check_signal_quality': 'Signal sifati',
  'tools.analyze_signals': 'Signallarni tahlil qilish',

  // ---------------------------------------------------------------------------
  // ticket.* — TicketForm
  // ---------------------------------------------------------------------------
  'ticket.conclusion.label': 'Xulosa',
  'ticket.conclusion.placeholder': 'Xulosani tasvirlang...',
  'ticket.urgency.label': 'Ustuvorlik',
  'ticket.urgency.low': 'Past',
  'ticket.urgency.medium': 'Oʻrtacha',
  'ticket.urgency.high': 'Yuqori',
  'ticket.ops.label': 'Amaliyotlar (bir qatorda bittadan)',
  'ticket.ops.placeholder': 'Moyni almashtirish\nTasmani tekshirish',
  'ticket.parts.label': 'Ehtiyot qismlar (majburiy emas, bir qatorda bittadan)',
  'ticket.parts.placeholder': 'Moy filtri, Havo filtri',
  'ticket.refs.label': 'Qoʻllanma havolalari',
  'ticket.ref.manual_placeholder': 'Qoʻllanma nomi',
  'ticket.ref.page_placeholder': 'B.',
  'ticket.ref.remove_title': 'Oʻchirish',
  'ticket.ref.add': '+ Havola qoʻshish',
  'ticket.submit': 'TOiR-ga yuborish',
  'ticket.submitting': 'Yuborilmoqda…',
  'ticket.cancel': 'Bekor qilish',
  'ticket.success': '{id} ariza yaratildi',
  'ticket.close': 'Yopish',
  'ticket.validation.conclusion': 'Xulosani kiriting',
  'ticket.validation.ops': 'Kamida bitta amaliyot koʻrsating',
  'ticket.validation.ref_manual': 'Havola #{n}: qoʻllanmani koʻrsating',
  'ticket.validation.ref_page': 'Havola #{n}: bet raqami ≥ 1 boʻlishi kerak',
  'ticket.error.create': 'Ariza yaratish xatosi',

  // ---------------------------------------------------------------------------
  // doc.* — DocPanel
  // ---------------------------------------------------------------------------
  'doc.page.title': 'b. {n}',
  'doc.loading': 'Yuklanmoqda…',
  'doc.error.unavailable': 'Sahifa serverda mavjud emas',
  'doc.error.generic': 'Xato: {msg}',
  'doc.error.load': 'Sahifani yuklash xatosi',
  'doc.empty': 'Sahifa matni mavjud emas — PDF ni oching',
  'doc.open_pdf': 'PDF ochish (b. {n})',

  // ---------------------------------------------------------------------------
  // fleet.* — FleetView
  // ---------------------------------------------------------------------------
  'fleet.group.normal': 'Normal',
  'fleet.group.attention': 'Eʼtibor',
  'fleet.group.quarantine': 'Karantin',
  'fleet.requires_attention': 'Eʼtibor kerak',
  'fleet.priority_list': 'Ustuvorlik roʻyxati',
  'fleet.no_anomalies': 'Anomaliyasiz',
  'fleet.open': 'Ochish',
  'fleet.retry': 'Takrorlash',
  'fleet.all_fleet': 'Butun park ({n})',
  'fleet.table.garage_no': 'Garaj raqami',
  'fleet.table.vehicle_id': 'Transport ID',
  'fleet.table.make_model': 'Marka / model',
  'fleet.table.engine': 'Dvigatel',
  'fleet.table.group': 'Guruh',
  'fleet.table.status': 'Holat',

  // ---------------------------------------------------------------------------
  // admin.* — AdminView
  // ---------------------------------------------------------------------------
  'admin.tab.dashboard': 'Dashboard',
  'admin.tab.users': 'Foydalanuvchilar',
  'admin.tab.llm': 'LLM sozlamalari',
  'admin.dashboard.title': 'Foydalanish dashboardi',
  'admin.stat.requests': 'Soʻrovlar',
  'admin.stat.errors': 'Xatolar',
  'admin.stat.input_tokens': 'Kiruvchi tokenlar',
  'admin.stat.output_tokens': 'Chiquvchi tokenlar',
  'admin.recent_requests': 'Soʻnggi soʻrovlar',
  'admin.refresh': 'Yangilash',
  'admin.loading': 'Yuklanmoqda…',
  'admin.table.time': 'Vaqt',
  'admin.table.user': 'Foydalanuvchi',
  'admin.table.kind': 'Turi',
  'admin.table.model': 'Model',
  'admin.table.vehicle_id': 'Transport ID',
  'admin.table.input_tokens': 'Kir.tokenlar',
  'admin.table.output_tokens': 'Chiq.tokenlar',
  'admin.table.duration': 'Davomiyligi (ms)',
  'admin.table.status': 'Holat',
  'admin.error_label': 'Xato',
  'admin.no_records': 'Yozuvlar yoʻq',
  'admin.users.title': 'Foydalanuvchilar',
  'admin.add_user': 'Foydalanuvchi qoʻshish',
  'admin.username_placeholder': 'Foydalanuvchi nomi',
  'admin.password_placeholder': 'Parol (min. 8)',
  'admin.create': 'Yaratish',
  'admin.table.name': 'Ism',
  'admin.table.role': 'Roli',
  'admin.table.change_password': 'Parolni oʻzgartirish',
  'admin.table.created_at': 'Yaratilgan sana',
  'admin.table.actions': 'Amallar',
  'admin.must_change_pw': 'parolni oʻzgartiradi',
  'admin.new_password_placeholder': 'Yangi parol',
  'admin.reset_password': 'Parolni tiklash',
  'admin.delete': 'Oʻchirish',
  'admin.no_users': 'Foydalanuvchilar yoʻq',
  'admin.loading_indicator': '…',
  'admin.settings.title': 'LLM sozlamalari',
  'admin.protocol_label': 'Protokol',
  'admin.base_url_label': 'Base URL',
  'admin.api_key_label': 'API kaliti',
  'admin.not_set': 'koʻrsatilmagan',
  'admin.api_key_hint': 'Kalit serverda saqlanadi va ochiq holda qaytarilmaydi',
  'admin.model_label': 'Model',
  'admin.temperature_label': 'Temperature (0–1)',
  'admin.max_output_tokens_label': 'Max output tokens',
  'admin.empty_no_limit': 'boʻsh = cheklovsiz',
  'admin.save': 'Saqlash',
  'admin.saving': 'Saqlanmoqda…',
  'admin.current_settings': 'Joriy sozlamalar',
  'admin.delete_user_title': 'Foydalanuvchini oʻchirish',
  'admin.delete_user_message': '«{username}» oʻchirilsinmi?',
  'admin.password_min_8': 'Parol kamida 8 ta belgidan iborat boʻlishi kerak',

  // ---------------------------------------------------------------------------
  // confirm.* — useConfirm defaults
  // ---------------------------------------------------------------------------
  'confirm.ok': 'Tasdiqlash',
  'confirm.cancel': 'Bekor qilish',
} satisfies Messages

export default uz
