import type { Messages } from '../index'

const kk = {
  'app.title': 'Сандық механик',
  'app.nav.garage': 'Гараж',
  'app.nav.chat': 'Чат',
  'app.nav.fleet': 'Парк',
  'app.nav.admin': 'Админ',
  'app.role.admin': 'админ',
  'app.role.user': 'пайдаланушы',
  'app.logout': 'Шығу',
  'app.stub.title': '«{page}» бөлімі',
  'app.stub.body': 'Келесі кезеңде пайда болады.',
  'login.username': 'Пайдаланушы атауы',
  'login.password': 'Құпия сөз',
  'login.placeholder.username': 'Атын енгізіңіз',
  'login.placeholder.password': 'Құпия сөзді енгізіңіз',
  'login.submit': 'Кіру',
  'login.submitting': 'Кіру…',
  'login.change.title': 'Құпия сөзді өзгертіңіз',
  'login.change.hint': 'Жалғастыру үшін жаңа құпия сөз орнатыңыз.',
  'login.change.old': 'Ескі құпия сөз',
  'login.change.new': 'Жаңа құпия сөз',
  'login.change.new.min': 'Минимум 8 таңба',
  'login.change.repeat': 'Жаңа құпия сөзді қайталаңыз',
  'login.change.save': 'Құпия сөзді сақтау',
  'login.change.saving': 'Сақталуда…',
  'login.error.fillAll': 'Барлық өрістерді толтырыңыз',
  'login.error.min8': 'Жаңа құпия сөз: минимум 8 таңба',
  'login.error.mismatch': 'Құпия сөздер сәйкес келмейді',
  'login.error.password': 'Кіру қатесі',
  'login.error.change': 'Құпия сөз өзгерту қатесі',
  'login.adminHint': 'Бастапқы admin құпия сөзі алғашқы іске қосуда сервер консолінде шығарылады.',
  'login.consent': 'Демонстрациялық жүйеде деректерді өңдеуге келісемін (деректер синтетикалық, 152-ФЗ)',

  // ---------------------------------------------------------------------------
  // garage.* — GarageView
  // ---------------------------------------------------------------------------
  'garage.search.placeholder': 'Мемл. нөмір, гараж №, марка, модель…',
  'garage.filter.all': 'Барлығы',
  'garage.filter.normal': 'Қалыпты',
  'garage.filter.attention': 'Назар аудару қажет',
  'garage.filter.quarantine': 'Карантин',
  'garage.empty': 'Ештеңе табылмады',
  'garage.counts_anomalies': 'Ауытқулар: {n}',
  'garage.counts_checks': 'Тексерулер: {m}',

  // ---------------------------------------------------------------------------
  // status.* — StatusCard
  // ---------------------------------------------------------------------------
  'status.label.normal': 'Қалыпты',
  'status.label.anomaly': 'Ауытқу',
  'status.label.check_failed': 'Жазбада қате',
  'status.score.label': 'Баға',
  'status.confidence.label': 'Сенімділік',
  'status.signal.label': 'Сигнал сапасы:',
  'status.signal.good': 'Сенімді жазба',
  'status.signal.warning': 'Кедергілер',
  'status.signal.bad': 'Жазба жарамсыз',
  'status.check_failed_warning': 'Жазба жарамсыз — диагноз қойылмайды, жазбаны қайталаңыз',

  // ---------------------------------------------------------------------------
  // history.* — HistoryPanel
  // ---------------------------------------------------------------------------
  'history.title': 'Көлік тарихы',
  'history.checks_section': 'Тексерулер',
  'history.tickets_section': 'Өтініштер',
  'history.no_checks': 'Тексерулер әлі болған жоқ',
  'history.no_tickets': 'Өтініштер жоқ',
  'history.urgency.high': 'Жоғары',
  'history.urgency.medium': 'Орташа',
  'history.urgency.low': 'Төмен',

  // ---------------------------------------------------------------------------
  // chart.* — AnomalyChart
  // ---------------------------------------------------------------------------
  'chart.title': 'anomaly_score соңғы тексерулер бойынша',
  'chart.no_data': 'Графикке деректер жеткіліксіз',
  'chart.caption': 'Тарих көрсетіледі; болжам орындалмайды.',

  // ---------------------------------------------------------------------------
  // chat.* — ChatView
  // ---------------------------------------------------------------------------
  'chat.back': 'Артқа',
  'chat.new_dialog': 'Жаңа диалог',
  'chat.history': 'Тарих',
  'chat.document': 'Құжат',
  'chat.select_doc': 'Чаттан құжат таңдаңыз',
  'chat.streaming': 'Жасанды интеллект жазуда...',
  'chat.input.placeholder': 'Хабарлама енгізіңіз...',
  'chat.stop': 'Тоқтату',
  'chat.quick.diagnostic.label': 'Диагностика алу',
  'chat.quick.diagnostic.text': 'Диагностика нәтижесін алу',
  'chat.quick.can_move.label': 'Жылжытуға бола ма?',
  'chat.quick.can_move.text': 'Көлікті өз күшімен базаға жылжытуға бола ма?',
  'chat.quick.ticket.label': 'Өтініш жасау',
  'chat.quick.ticket.text': 'Ақаулық туралы өтініш жасаңыз',
  'chat.error.connection': 'Байланыс қатесі',
  'chat.mic.label': 'Дауыспен енгізу',
  'chat.mic.listening': 'Тыңдау…',
  'chat.empty_vehicle': 'Парктен өтінішті таңдаңыз немесе тарихтан чатты ашыңыз',
  'chat.reasoning.toggle': 'Ойлану…',

  // ---------------------------------------------------------------------------
  // tools.* — AgentStep tool-name display map
  // ---------------------------------------------------------------------------
  'tools.get_diagnostic_result': 'Диагностика',
  'tools.get_vehicle_info': 'Көлік туралы ақпарат',
  'tools.search_rag': 'Базада іздеу',
  'tools.create_ticket': 'Өтініш жасау',
  'tools.check_signal_quality': 'Сигнал сапасы',
  'tools.analyze_signals': 'Сигналдарды талдау',

  // ---------------------------------------------------------------------------
  // ticket.* — TicketForm
  // ---------------------------------------------------------------------------
  'ticket.conclusion.label': 'Қорытынды',
  'ticket.conclusion.placeholder': 'Қорытындыны сипаттаңыз...',
  'ticket.urgency.label': 'Басымдық',
  'ticket.urgency.low': 'Төмен',
  'ticket.urgency.medium': 'Орташа',
  'ticket.urgency.high': 'Жоғары',
  'ticket.ops.label': 'Операциялар (жол сайын бір)',
  'ticket.ops.placeholder': 'Майды ауыстыру\nТаспаны тексеру',
  'ticket.parts.label': 'Бөлшектер (міндетті емес, жол сайын бір)',
  'ticket.parts.placeholder': 'Май фильтрі, Ауа фильтрі',
  'ticket.refs.label': 'Нұсқаулық сілтемелері',
  'ticket.ref.manual_placeholder': 'Нұсқаулық атауы',
  'ticket.ref.page_placeholder': 'Бет.',
  'ticket.ref.remove_title': 'Жою',
  'ticket.ref.add': '+ Сілтеме қосу',
  'ticket.submit': 'ТОиР-ге жіберу',
  'ticket.submitting': 'Жіберілуде…',
  'ticket.cancel': 'Болдырмау',
  'ticket.success': '{id} өтініш жасалды',
  'ticket.close': 'Жабу',
  'ticket.validation.conclusion': 'Қорытындыны енгізіңіз',
  'ticket.validation.ops': 'Кем дегенде бір операция көрсетіңіз',
  'ticket.validation.ref_manual': 'Сілтеме #{n}: нұсқаулықты көрсетіңіз',
  'ticket.validation.ref_page': 'Сілтеме #{n}: бет кемінде 1 болуы керек',
  'ticket.error.create': 'Өтініш жасау қатесі',

  // ---------------------------------------------------------------------------
  // doc.* — DocPanel
  // ---------------------------------------------------------------------------
  'doc.page.title': 'бет. {n}',
  'doc.loading': 'Жүктелуде…',
  'doc.error.unavailable': 'Бет серверде қолжетімсіз',
  'doc.error.generic': 'Қате: {msg}',
  'doc.error.load': 'Бетті жүктеу қатесі',
  'doc.empty': 'Бет мәтіні қолжетімсіз — PDF ашыңыз',
  'doc.open_pdf': 'PDF ашу (бет. {n})',

  // ---------------------------------------------------------------------------
  // fleet.* — FleetView
  // ---------------------------------------------------------------------------
  'fleet.group.normal': 'Қалыпты',
  'fleet.group.attention': 'Назар аудару',
  'fleet.group.quarantine': 'Карантин',
  'fleet.requires_attention': 'Назар аудару қажет',
  'fleet.priority_list': 'Басымдық тізімі',
  'fleet.no_anomalies': 'Ауытқусыз',
  'fleet.open': 'Ашу',
  'fleet.retry': 'Қайталау',
  'fleet.all_fleet': 'Барлық парк ({n})',
  'fleet.table.garage_no': 'Гараж №',
  'fleet.table.vehicle_id': 'Көлік ID',
  'fleet.table.make_model': 'Марка / модель',
  'fleet.table.engine': 'Қозғалтқыш',
  'fleet.table.group': 'Топ',
  'fleet.table.status': 'Статус',

  // ---------------------------------------------------------------------------
  // admin.* — AdminView
  // ---------------------------------------------------------------------------
  'admin.tab.dashboard': 'Дашборд',
  'admin.tab.users': 'Пайдаланушылар',
  'admin.tab.llm': 'LLM баптаулары',
  'admin.dashboard.title': 'Пайдалану дашборды',
  'admin.stat.requests': 'Сұраныстар',
  'admin.stat.errors': 'Қателер',
  'admin.stat.input_tokens': 'Кіріс токендері',
  'admin.stat.output_tokens': 'Шығыс токендері',
  'admin.recent_requests': 'Соңғы сұраныстар',
  'admin.refresh': 'Жаңарту',
  'admin.loading': 'Жүктелуде…',
  'admin.table.time': 'Уақыт',
  'admin.table.user': 'Пайдаланушы',
  'admin.table.kind': 'Түрі',
  'admin.table.model': 'Модель',
  'admin.table.vehicle_id': 'Көлік ID',
  'admin.table.input_tokens': 'Кіріс токендері',
  'admin.table.output_tokens': 'Шығыс токендері',
  'admin.table.duration': 'Ұзақтық (мс)',
  'admin.table.status': 'Статус',
  'admin.error_label': 'Қате',
  'admin.no_records': 'Жазбалар жоқ',
  'admin.users.title': 'Пайдаланушылар',
  'admin.add_user': 'Пайдаланушы қосу',
  'admin.username_placeholder': 'Пайдаланушы атауы',
  'admin.password_placeholder': 'Құпия сөз (мин. 8)',
  'admin.create': 'Жасау',
  'admin.table.name': 'Аты',
  'admin.table.role': 'Рөл',
  'admin.table.change_password': 'Құпия сөзді өзгерту',
  'admin.table.created_at': 'Жасалған күні',
  'admin.table.actions': 'Әрекеттер',
  'admin.must_change_pw': 'құпия сөзді өзгертеді',
  'admin.new_password_placeholder': 'Жаңа құпия сөз',
  'admin.reset_password': 'Құпия сөзді қалпына келтіру',
  'admin.delete': 'Жою',
  'admin.no_users': 'Пайдаланушылар жоқ',
  'admin.loading_indicator': '…',
  'admin.settings.title': 'LLM баптаулары',
  'admin.protocol_label': 'Протокол',
  'admin.base_url_label': 'Base URL',
  'admin.api_key_label': 'API кілті',
  'admin.not_set': 'көрсетілмеген',
  'admin.api_key_hint': 'Кілт серверде сақталады және ашық түрде қайтарылмайды',
  'admin.model_label': 'Модель',
  'admin.temperature_label': 'Temperature (0–1)',
  'admin.max_output_tokens_label': 'Max output tokens',
  'admin.empty_no_limit': 'бос = лимитсіз',
  'admin.save': 'Сақтау',
  'admin.saving': 'Сақталуда…',
  'admin.current_settings': 'Ағымдағы баптаулар',
  'admin.delete_user_title': 'Пайдаланушыны жою',
  'admin.delete_user_message': '«{username}» жойылсын ба?',
  'admin.password_min_8': 'Құпия сөз кем дегенде 8 таңбадан тұруы керек',

  // ---------------------------------------------------------------------------
  // confirm.* — useConfirm defaults
  // ---------------------------------------------------------------------------
  'confirm.ok': 'Растау',
  'confirm.cancel': 'Болдырмау',
} satisfies Messages

export default kk
