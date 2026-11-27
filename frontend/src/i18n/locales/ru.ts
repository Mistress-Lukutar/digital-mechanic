const ru = {
  'app.title': 'Цифровой механик',
  'app.nav.garage': 'Гараж',
  'app.nav.chat': 'Чат',
  'app.nav.fleet': 'Парк',
  'app.nav.admin': 'Админ',
  'app.role.admin': 'админ',
  'app.role.user': 'пользователь',
  'app.logout': 'Выйти',
  'app.stub.title': 'Раздел «{page}»',
  'app.stub.body': 'Появится в следующем этапе.',
  'login.username': 'Имя пользователя',
  'login.password': 'Пароль',
  'login.placeholder.username': 'Введите имя',
  'login.placeholder.password': 'Введите пароль',
  'login.submit': 'Войти',
  'login.submitting': 'Вход…',
  'login.change.title': 'Смените пароль',
  'login.change.hint': 'Для продолжения установите новый пароль.',
  'login.change.old': 'Старый пароль',
  'login.change.new': 'Новый пароль',
  'login.change.new.min': 'Минимум 8 символов',
  'login.change.repeat': 'Повторите новый пароль',
  'login.change.save': 'Сохранить пароль',
  'login.change.saving': 'Сохранение…',
  'login.error.fillAll': 'Заполните все поля',
  'login.error.min8': 'Новый пароль: минимум 8 символов',
  'login.error.mismatch': 'Пароли не совпадают',
  'login.error.password': 'Ошибка входа',
  'login.error.change': 'Ошибка смены пароля',
  'login.consent': 'Согласен на обработку данных в демонстрационной системе (данные синтетические, 152-ФЗ)',

  // ---------------------------------------------------------------------------
  // garage.* — GarageView
  // ---------------------------------------------------------------------------
  'garage.search.placeholder': 'Госномер, гаражный №, марка, модель…',
  'garage.filter.all': 'Все',
  'garage.filter.normal': 'В норме',
  'garage.filter.attention': 'Проблемы записи',
  'garage.filter.quarantine': 'Карантин',
  'garage.empty': 'Ничего не найдено',
  'garage.counts_anomalies': 'Отклонений: {n}',
  'garage.counts_checks': 'Проверок: {m}',
  'garage.vehicle_id': 'Госномер',
  'garage.fuel.diesel': 'дизель',
  'garage.fuel.petrol': 'бензин',

  // ---------------------------------------------------------------------------
  // status.* — StatusCard
  // ---------------------------------------------------------------------------
  'status.label.normal': 'Норма',
  'status.label.anomaly': 'Отклонение',
  'status.label.check_failed': 'Сбой записи',
  'status.score.label': 'Балл',
  'status.confidence.label': 'Уверенность',
  'status.signal.label': 'Качество сигнала:',
  'status.signal.good': 'Надёжная запись',
  'status.signal.warning': 'Помехи',
  'status.signal.bad': 'Запись непригодна',
  'status.check_failed_warning': 'Запись непригодна — диагноз не ставится, повторите запись',

  // ---------------------------------------------------------------------------
  // history.* — HistoryPanel
  // ---------------------------------------------------------------------------
  'history.title': 'История ТС',
  'history.checks_section': 'Проверки',
  'history.tickets_section': 'Заявки',
  'history.no_checks': 'Проверок ещё не было',
  'history.no_tickets': 'Заявок нет',
  'history.urgency.high': 'Высокий',
  'history.urgency.medium': 'Средний',
  'history.urgency.low': 'Низкий',
  'history.trend_worsening': 'Score растёт {n} проверок подряд — состояние ухудшается',
  'history.trend_improving': 'Score снижается {n} проверок подряд — состояние улучшается',
  'history.trend_stable': 'Score стабилен — без признаков ухудшения',
  'history.ticket_details': 'Заявка {id}',
  'history.page_abbr': 'стр.',
  'history.conclusion': 'Заключение',
  'history.urgency_label': 'Приоритет',
  'history.anomaly_type': 'Тип отклонения',
  'history.operations': 'Операции',
  'history.spare_parts': 'Запчасти',
  'history.references': 'Ссылки на руководство',
  'history.priority_rationale': 'Обоснование приоритета',

  // ---------------------------------------------------------------------------
  // chart.* — AnomalyChart
  // ---------------------------------------------------------------------------
  'chart.title': 'anomaly_score по последним проверкам',
  'chart.no_data': 'Недостаточно данных для графика',
  // ---------------------------------------------------------------------------
  // chat.* — ChatView
  // ---------------------------------------------------------------------------
  'chat.back': 'Назад',
  'chat.new_dialog': 'Новый диалог',
  'chat.history': 'История',
  'chat.document': 'Документ',
  'chat.select_doc': 'Выберите документ из чата',
  'chat.streaming': 'ИИ печатает...',
  'chat.input.placeholder': 'Введите сообщение...',
  'chat.stop': 'Стоп',
  'chat.quick.diagnostic.label': 'Получить диагностику',
  'chat.quick.diagnostic.text': 'Получить результат диагностики',
  'chat.quick.can_move.label': 'Можно ли перегнать?',
  'chat.quick.can_move.text': 'Можно ли перегнать машину своим ходом на базу?',
  'chat.quick.ticket.label': 'Создать заявку',
  'chat.quick.ticket.text': 'Создай заявку на дефектовку',
  'chat.error.connection': 'Ошибка соединения',
  'chat.mic.label': 'Голосовой ввод',
  'chat.mic.listening': 'Слушаю…',
  'chat.empty_vehicle': 'Выберите заявку в парке или откройте чат из истории',
  'chat.reasoning.toggle': 'Думаю…',
  'chat.attach.label': 'Прикрепить изображение',
  'chat.attach.remove': 'Убрать изображение',

  // ---------------------------------------------------------------------------
  // chats.* — ChatsPanel
  // ---------------------------------------------------------------------------
  'chats.tab': 'Чаты',
  'chats.empty': 'Диалогов ещё нет',
  'chats.untitled': 'Без названия',
  'chats.loading': 'Загрузка…',
  'chats.delete': 'Удалить чат',
  'chats.delete_confirm': 'Удалить этот диалог? История сообщений будет потеряна.',

  // ---------------------------------------------------------------------------
  // tools.* — AgentStep tool-name display map
  // ---------------------------------------------------------------------------
  'tools.get_diagnostic_result': 'Диагностика',
  'tools.get_vehicle_info': 'Информация ТС',
  'tools.search_rag': 'Поиск в базе',
  'tools.create_ticket': 'Создание заявки',
  'tools.check_signal_quality': 'Качество сигнала',
  'tools.analyze_signals': 'Анализ сигналов',

  // ---------------------------------------------------------------------------
  // ticket.* — TicketForm
  // ---------------------------------------------------------------------------
  'ticket.conclusion.label': 'Заключение',
  'ticket.conclusion.placeholder': 'Опишите заключение...',
  'ticket.urgency.label': 'Приоритет',
  'ticket.urgency.low': 'Низкий',
  'ticket.urgency.medium': 'Средний',
  'ticket.urgency.high': 'Высокий',
  'ticket.ops.label': 'Операции (по одной на строку)',
  'ticket.ops.placeholder': 'Замена масла\nПроверка ремня',
  'ticket.parts.label': 'Запчасти (необязательно, по одной на строку)',
  'ticket.parts.placeholder': 'Фильтр масляный, Фильтр воздушный',
  'ticket.refs.label': 'Ссылки на руководство',
  'ticket.ref.manual_placeholder': 'Название руководства',
  'ticket.ref.page_placeholder': 'Стр.',
  'ticket.ref.remove_title': 'Удалить',
  'ticket.ref.add': '+ Добавить ссылку',
  'ticket.submit': 'Подать в ТОиР',
  'ticket.submitting': 'Отправка…',
  'ticket.cancel': 'Отмена',
  'ticket.success': 'Заявка {id} создана',
  'ticket.close': 'Закрыть',
  'ticket.validation.conclusion': 'Введите заключение',
  'ticket.validation.ops': 'Укажите хотя бы одну операцию',
  'ticket.validation.ref_manual': 'Ссылка #{n}: укажите руководство',
  'ticket.validation.ref_page': 'Ссылка #{n}: страница должна быть ≥ 1',
  'ticket.error.create': 'Ошибка создания заявки',

  // ---------------------------------------------------------------------------
  // doc.* — DocPanel
  // ---------------------------------------------------------------------------
  'doc.page.title': 'стр. {n} из {m}',
  'doc.loading': 'Загрузка…',
  'doc.error.unavailable': 'PDF-файл недоступен на сервере',
  'doc.error.generic': 'Ошибка: {msg}',
  'doc.prev_page': 'Предыдущая страница',
  'doc.next_page': 'Следующая страница',
  'doc.zoom_in': 'Увеличить',
  'doc.zoom_out': 'Уменьшить',

  // ---------------------------------------------------------------------------
  // fleet.* — FleetView
  // ---------------------------------------------------------------------------
  'fleet.group.normal': 'Норма',
  'fleet.group.attention': 'Внимание',
  'fleet.group.quarantine': 'Карантин',
  'fleet.requires_attention': 'Проблемы записи',
  'fleet.priority_list': 'Приоритетный список',
  'fleet.no_anomalies': 'Без отклонений',
  'fleet.open': 'Открыть',
  'fleet.retry': 'Повторить',
  'fleet.all_fleet': 'Весь парк ({n})',
  'fleet.table.garage_no': 'Гаражный №',
  'fleet.table.vehicle_id': 'ID ТС',
  'fleet.table.make_model': 'Марка / модель',
  'fleet.table.engine': 'Двигатель',
  'fleet.table.group': 'Группа',
  'fleet.table.status': 'Статус',
  'fleet.filtered_title': 'Фильтр: {label} ({n})',
  'fleet.empty_group': 'В этой категории нет машин',

  // ---------------------------------------------------------------------------
  // admin.* — AdminView
  // ---------------------------------------------------------------------------
  'admin.tab.dashboard': 'Дашборд',
  'admin.tab.users': 'Пользователи',
  'admin.tab.llm': 'Настройки LLM',
  'admin.dashboard.title': 'Дашборд использования',
  'admin.stat.requests': 'Запросов',
  'admin.stat.errors': 'Ошибок',
  'admin.stat.input_tokens': 'Входящие токены',
  'admin.stat.output_tokens': 'Исходящие токены',
  'admin.recent_requests': 'Последние запросы',
  'admin.refresh': 'Обновить',
  'admin.loading': 'Загрузка…',
  'admin.table.time': 'Время',
  'admin.table.user': 'Пользователь',
  'admin.table.kind': 'Тип',
  'admin.table.model': 'Модель',
  'admin.table.vehicle_id': 'ID ТС',
  'admin.table.input_tokens': 'Вх. токены',
  'admin.table.output_tokens': 'Исх. токены',
  'admin.table.duration': 'Длительность (мс)',
  'admin.table.status': 'Статус',
  'admin.error_label': 'Ошибка',
  'admin.no_records': 'Записей нет',
  'admin.users.title': 'Пользователи',
  'admin.add_user': 'Добавить пользователя',
  'admin.username_placeholder': 'Имя пользователя',
  'admin.password_placeholder': 'Пароль (мин. 8)',
  'admin.create': 'Создать',
  'admin.table.name': 'Имя',
  'admin.table.role': 'Роль',
  'admin.table.change_password': 'Смена пароля',
  'admin.table.created_at': 'Дата создания',
  'admin.table.actions': 'Действия',
  'admin.must_change_pw': 'сменит пароль',
  'admin.new_password_placeholder': 'Новый пароль',
  'admin.reset_password': 'Сбросить пароль',
  'admin.delete': 'Удалить',
  'admin.no_users': 'Пользователей нет',
  'admin.loading_indicator': '…',
  'admin.settings.title': 'Настройки LLM',
  'admin.protocol_label': 'Протокол',
  'admin.base_url_label': 'Base URL',
  'admin.api_key_label': 'API ключ',
  'admin.not_set': 'не задан',
  'admin.api_key_hint': 'Ключ хранится на сервере и не возвращается в открытом виде',
  'admin.model_label': 'Модель',
  'admin.temperature_label': 'Temperature (0–1)',
  'admin.max_output_tokens_label': 'Max output tokens',
  'admin.empty_no_limit': 'пусто = без лимита',
  'admin.save': 'Сохранить',
  'admin.saving': 'Сохранение…',
  'admin.current_settings': 'Текущие настройки',
  'admin.delete_user_title': 'Удалить пользователя',
  'admin.delete_user_message': 'Удалить «{username}»',
  'admin.password_min_8': 'Пароль должен содержать минимум 8 символов',
  'admin.detail_question': 'Вопрос',
  'admin.detail_answer': 'Ответ',
  'admin.detail_tools': 'Инструменты',
  'admin.detail_citations': 'Цитаты',
  'admin.detail_ticket_draft': 'Черновик заявки',
  'admin.detail_image': 'с изображением',
  'admin.detail_hint': 'Клик по строке «chat» — вопрос, ответ и цитаты хода',
  'admin.detail_loading': 'Загрузка…',
  'admin.detail_error': 'Детализация недоступна',

  // ---------------------------------------------------------------------------
  // confirm.* — useConfirm defaults
  // ---------------------------------------------------------------------------
  'confirm.ok': 'Подтвердить',
  'confirm.cancel': 'Отмена',

  // ---------------------------------------------------------------------------
  // config.* — config-status warning banner
  // ---------------------------------------------------------------------------
  'config.warning_title': 'Проблемы с конфигурацией системы',
  'config.dismiss': 'Скрыть',
} satisfies Record<string, string>

export default ru
