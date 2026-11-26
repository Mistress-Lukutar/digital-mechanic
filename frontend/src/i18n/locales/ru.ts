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
  'login.adminHint': 'Стартовый пароль admin печатается в консоль сервера при первом запуске.',

  // ---------------------------------------------------------------------------
  // garage.* — GarageView
  // ---------------------------------------------------------------------------
  'garage.search.placeholder': 'Госномер, гаражный №, марка, модель…',
  'garage.filter.all': 'Все',
  'garage.filter.normal': 'В норме',
  'garage.filter.attention': 'Требует внимания',
  'garage.filter.quarantine': 'Карантин',
  'garage.empty': 'Ничего не найдено',
  'garage.counts_anomalies': 'Отклонений: {n}',
  'garage.counts_checks': 'Проверок: {m}',

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

  // ---------------------------------------------------------------------------
  // chart.* — AnomalyChart
  // ---------------------------------------------------------------------------
  'chart.title': 'anomaly_score по последним проверкам',
  'chart.no_data': 'Недостаточно данных для графика',
  'chart.caption': 'Отображение истории; прогноз не выполняется.',
} satisfies Record<string, string>

export default ru
