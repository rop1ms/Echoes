// Native launcher surface. Python is only the download/install backend bridge.
#include <QtWidgets/QApplication>
#include <QtWidgets/QWidget>
#include <QtWidgets/QLabel>
#include <QtWidgets/QPushButton>
#include <QtWidgets/QComboBox>
#include <QtWidgets/QCheckBox>
#include <QtWidgets/QLineEdit>
#include <QtWidgets/QProgressBar>
#include <QtWidgets/QPlainTextEdit>
#include <QtWidgets/QStackedWidget>
#include <QtWidgets/QVBoxLayout>
#include <QtWidgets/QHBoxLayout>
#include <QtWidgets/QFileDialog>
#include <QtWidgets/QMessageBox>
#include <QtWidgets/QMenu>
#include <QtGui/QPainter>
#include <QtGui/QCloseEvent>
#include <QtGui/QDesktopServices>
#include <QtGui/QIcon>
#include <QtGui/QFontDatabase>
#include <QtGui/QImage>
#include <QtCore/QJsonArray>
#include <QtCore/QJsonDocument>
#include <QtCore/QJsonObject>
#include <QtCore/QSettings>
#include <QtCore/QFile>
#include <QtCore/QFileInfo>
#include <QtCore/QDir>
#include <QtCore/QUrl>
#include <QtCore/QRegularExpression>
#include <QtCore/QStorageInfo>
#include <vector>
#include <cmath>

#define API extern "C" __declspec(dllexport)
using Callback = void (*)(const char *);
static Callback callback = nullptr;

struct Text { const char *key; const char *en; const char *ru; };
static const Text texts[] = {
    {"brand.platform", "Music player for Windows", "Музыкальный плеер для Windows"},
    {"header.launcher", "Launcher", "Лаунчер"},
    {"language.label", "Interface language", "Язык интерфейса"},
    {"language.manage", "Translation files", "Файлы перевода"},
    {"language.import", "Load a translation…", "Загрузить перевод…"},
    {"language.export", "Save English template…", "Сохранить английский шаблон…"},
    {"language.invalid", "This translation file is invalid. Use the English template and keep its placeholders unchanged.", "Неверный файл перевода. Используйте английский шаблон и сохраните его подстановки без изменений."},
    {"language.loaded", "Translation loaded. Missing entries use English.", "Перевод загружен. Пропущенные строки отображаются на английском."},
    {"language.save_error", "The translation file could not be saved.", "Не удалось сохранить файл перевода."},
    {"home.ready", "Play music.", "Слушать музыку."},
    {"home.location", "INSTALL LOCATION", "ПАПКА УСТАНОВКИ"},
    {"home.installed", "Installed · {version}", "Установлена · {version}"},
    {"home.new", "Available · {version}", "Доступна · {version}"},
    {"home.latest", "You're up to date.", "Установлена последняя версия."},
    {"home.checking", "Checking GitHub for updates…", "Проверяем обновления на GitHub…"},
    {"home.offline", "Could not check GitHub. Your installed player is ready to use.", "Не удалось проверить GitHub. Установленным плеером можно пользоваться."},
    {"home.launching", "Opening ECHOES…", "Открываем ECHOES…"},
    {"button.launch", "Open ECHOES", "Запустить ECHOES"},
    {"button.update", "Update to {version}", "Обновить до {version}"},
    {"button.app_folder", "App folder", "Папка программы"},
    {"button.data_folder", "My data", "Мои данные"},
    {"button.reinstall", "Reinstall…", "Переустановить…"},
    {"button.uninstall", "Uninstall", "Удалить"},
    {"button.back", "Back", "Назад"},
    {"button.change", "Change…", "Изменить…"},
    {"button.install", "Download & install", "Скачать и установить"},
    {"progress.complete", "{percent}% complete", "Готово {percent}%"},
    {"button.details", "Installation details", "Подробности установки"},
    {"button.home", "Back to launcher", "К лаунчеру"},
    {"setup.title", "Install ECHOES.", "Установить ECHOES."},
    {"setup.subtitle", "Installs for your Windows account. Administrator access is unnecessary.", "Установка для вашего профиля Windows. Права администратора не требуются."},
    {"setup.location", "INSTALL LOCATION", "ПАПКА УСТАНОВКИ"},
    {"setup.choose", "Choose an installation folder", "Выберите папку установки"},
    {"setup.space", "{space} GB free · around 1 GB needed", "Свободно {space} ГБ · потребуется около 1 ГБ"},
    {"setup.space_unknown", "Around 1 GB of free space needed", "Потребуется около 1 ГБ свободного места"},
    {"setup.options", "SETUP OPTIONS", "ПАРАМЕТРЫ УСТАНОВКИ"},
    {"option.desktop", "Desktop shortcut", "Ярлык на рабочем столе"},
    {"option.menu", "Start menu shortcuts", "Ярлыки в меню «Пуск»"},
    {"option.spotify", "Additional Spotify downloader (spotdl)", "Дополнительный загрузчик Spotify (spotdl)"},
    {"option.autostart", "Open ECHOES when Windows starts", "Запускать ECHOES вместе с Windows"},
    {"option.launch", "Open ECHOES after installation", "Открыть ECHOES после установки"},
    {"progress.install", "Installing ECHOES.", "Установка ECHOES."},
    {"progress.update", "Updating ECHOES.", "Обновление ECHOES."},
    {"progress.download", "Downloading the latest ECHOES from GitHub…", "Скачиваем последнюю версию ECHOES с GitHub…"},
    {"progress.unpack", "Preparing the installation files…", "Подготавливаем файлы установки…"},
    {"progress.installing", "Installing ECHOES and its components…", "Устанавливаем ECHOES и его компоненты…"},
    {"progress.updating", "Updating ECHOES and its components…", "Обновляем ECHOES и его компоненты…"},
    {"done.install", "ECHOES is installed.", "ECHOES установлен."},
    {"done.update", "ECHOES is updated.", "ECHOES обновлён."},
    {"error.title", "Something went wrong", "Что-то пошло не так"},
    {"error.backend", "The operation could not be completed. Check your connection and the installation details.", "Не удалось завершить действие. Проверьте интернет и подробности установки."},
    {"error.running", "ECHOES is already open. Look for its window or the tray icon.", "ECHOES уже открыт. Найдите его окно или значок в трее."},
    {"error.missing", "ECHOES was not found in this folder.", "ECHOES не найден в этой папке."},
    {"error.busy", "Please let the installation finish before closing the launcher.", "Дождитесь завершения установки перед закрытием лаунчера."},
    {"uninstall.question", "Open the ECHOES uninstaller? You can choose to keep your music and settings there.", "Открыть удаление ECHOES? Там можно оставить музыку и настройки."},
    {"dialog.yes", "Continue", "Продолжить"},
    {"dialog.no", "Cancel", "Отмена"},
};

static QJsonObject english() {
    QJsonObject o;
    for (const auto &t : texts) o[t.key] = QString::fromUtf8(t.en);
    return o;
}
static bool isNewer(const QString &remote,const QString &installed) {
    auto parts=[](const QString &value){std::vector<int> result;auto m=QRegularExpression("\\d+").globalMatch(value);while(m.hasNext())result.push_back(m.next().captured().toInt());return result;};
    return !remote.isEmpty()&&parts(remote)>parts(installed);
}
static QStringList tokens(const QString &s) {
    QStringList out;
    auto matches = QRegularExpression("\\{[a-z]+\\}").globalMatch(s);
    while (matches.hasNext()) out << matches.next().captured();
    out.sort(); return out;
}
static bool parsePack(const QByteArray &bytes, QJsonObject &out, QString &name) {
    if (bytes.isEmpty() || bytes.size() > 256 * 1024) return false;
    QJsonParseError error;
    const auto doc = QJsonDocument::fromJson(bytes, &error);
    if (error.error != QJsonParseError::NoError || !doc.isObject()) return false;
    auto obj = doc.object();
    if (obj["format"].toInt() != 1 || !obj["name"].isString() || !obj["translations"].isObject()) return false;
    name = obj["name"].toString().trimmed();
    if (name.isEmpty() || name.size() > 60) return false;
    auto input = obj["translations"].toObject();
    auto base = english();
    for (auto it = input.begin(); it != input.end(); ++it) {
        if (!base.contains(it.key())) continue;
        if (!it->isString()) return false;
        const QString value = it->toString();
        if (value.trimmed().isEmpty() || value.size() > 4000 || tokens(value) != tokens(base[it.key()].toString())) return false;
        out[it.key()] = value;
    }
    return !out.isEmpty();
}

class Brand final : public QWidget {
public:
    QString platform;
    Brand(const QString &markFile, const QString &displayFamily, QWidget *parent)
        : QWidget(parent), displayFamily(displayFamily) {
        setMinimumWidth(360);
        setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Expanding);

        QImage mask(markFile);
        if (mask.isNull()) return;
        mask = mask.scaledToWidth(640, Qt::SmoothTransformation).convertToFormat(QImage::Format_ARGB32);
        steel = QImage(mask.size(), QImage::Format_ARGB32);
        for (int y = 0; y < mask.height(); ++y) {
            auto *row = reinterpret_cast<QRgb *>(steel.scanLine(y));
            const auto *alpha = reinterpret_cast<const QRgb *>(mask.constScanLine(y));
            for (int x = 0; x < mask.width(); ++x) {
                const double u = double(x) / mask.width(), v = double(y) / mask.height();
                const double reflection = .68 + .23 * std::sin(21 * u - 9 * v) + .12 * std::sin(47 * u + 31 * v);
                const int grain = int((quint32(x) * 1664525u ^ quint32(y) * 1013904223u) % 29u) - 14;
                const int tone = qBound(40, int(255 * reflection) + grain, 255);
                row[x] = qRgba(tone, tone, tone, qAlpha(alpha[x]));
            }
        }
    }
protected:
    void paintEvent(QPaintEvent *) override {
        QPainter painter(this);
        painter.setRenderHints(QPainter::Antialiasing | QPainter::SmoothPixmapTransform);
        const QRectF frame = QRectF(rect()).adjusted(28, 26, -28, -26);
        QRadialGradient light(QPointF(width() * .56, height() * .40), height() * .67);
        light.setColorAt(0, QColor("#242422"));
        light.setColorAt(.61, QColor("#121212"));
        light.setColorAt(1, QColor("#090909"));
        painter.fillRect(rect(), light);

        painter.setPen(QColor("#393835"));
        painter.drawRect(frame);
        const double baseline = frame.bottom() - 40;
        painter.drawLine(QPointF(frame.left(), baseline), QPointF(frame.right(), baseline));

        const double size = qMin(frame.width() - 25, frame.height() * .65);
        const QRectF art(frame.center().x() - size / 2, frame.top() + frame.height() * .075, size, size);
        const QRectF outline = art.adjusted(23, 19, -23, -19);
        painter.setPen(QColor("#2d2c2a"));
        painter.drawEllipse(outline);
        painter.drawLine(QPointF(art.center().x(), frame.top()), QPointF(art.center().x(), outline.top()));
        painter.drawImage(art, steel);

        QFont display(displayFamily);
        display.setPixelSize(qRound(qMin(frame.width() * .24, frame.height() * .17)));
        painter.setPen(QColor("#ece9e0"));
        painter.setFont(display);
        const auto wordmark = QRectF(frame.left(), art.bottom() - 10, frame.width(), baseline - art.bottom() + 10);
        painter.drawText(wordmark, Qt::AlignCenter, "Echoes");

        QFont caption("Consolas");
        caption.setPixelSize(12);
        painter.setFont(caption);
        painter.setPen(QColor("#afada5"));
        painter.drawText(QRectF(frame.left() + 12, baseline, frame.width() - 24, 40), Qt::AlignCenter, platform);
    }
private:
    QString displayFamily;
    QImage steel;
};

class Launcher final : public QWidget {
public:
    explicit Launcher(const QJsonObject &state): QWidget(nullptr),
        store(state.contains("settings_path") ? state["settings_path"].toString() : QString("HKEY_CURRENT_USER\\Software\\ECHOES\\Launcher"),
              state.contains("settings_path") ? QSettings::IniFormat : QSettings::NativeFormat) {
        for (const auto &file : state["ui_fonts"].toArray())
            QFontDatabase::addApplicationFont(file.toString());
        const int displayId = QFontDatabase::addApplicationFont(state["display_font"].toString());
        const QString displayFamily = QFontDatabase::applicationFontFamilies(displayId).value(0, "Georgia");
        QApplication::setFont(QFont("Inter", 10));
        setObjectName("LauncherRoot");
        setWindowTitle("ECHOES Launcher");
        resize(1060, 680);
        setMinimumSize(930, 610);
        target=state["target"].toString();version=state["version"].toString();dataPath=state["data"].toString();
        if(target.isEmpty())target=store.value("installation",state["default"].toString()).toString();
        setWindowIcon(QIcon(state["icon"].toString()));
        language=store.value("language","en").toString();
        QJsonObject loaded;QString packName;
        if(parsePack(store.value("translation_pack").toByteArray(),loaded,packName)){custom=loaded;customName=packName;}
        if(language!="ru"&&language!="custom")language="en";
        if(language=="custom"&&custom.isEmpty())language="en";
        auto root = new QHBoxLayout(this);
        root->setContentsMargins(0, 0, 0, 0);
        root->setSpacing(0);
        brand = new Brand(state["mark"].toString(), displayFamily, this);
        root->addWidget(brand, 1);
        auto right = new QWidget(this);
        right->setObjectName("ControlPanel");
        auto column = new QVBoxLayout(right);
        column->setContentsMargins(34, 25, 34, 28);
        column->setSpacing(22);
        root->addWidget(right, 1);
        auto header = new QHBoxLayout;
        launcherLabel = new QLabel;
        launcherLabel->setObjectName("Eyebrow");
        header->addWidget(launcherLabel);
        header->addStretch();
        languages=new QComboBox;languages->setObjectName("Language");languages->setMinimumWidth(128);languages->addItem("English","en");languages->addItem(QString::fromUtf8("Русский"),"ru");
        if(!custom.isEmpty())languages->addItem(customName,"custom");
        languages->setCurrentIndex(languages->findData(language));header->addWidget(languages);
        languageFiles=new QPushButton("+");languageFiles->setObjectName("IconButton");languageFiles->setFixedSize(36,36);header->addWidget(languageFiles);column->addLayout(header);
        pages=new QStackedWidget;column->addWidget(pages,1);
        buildHome();buildSetup();buildProgress();buildDone();
        for(auto l:findChildren<QLabel*>())l->setTextFormat(Qt::PlainText);
        connect(languages,&QComboBox::currentIndexChanged,this,[this](int){language=languages->currentData().toString();store.setValue("language",language);applyText();});
        connect(languageFiles,&QPushButton::clicked,this,[this]{QMenu menu;auto load=menu.addAction(tr("language.import"));auto save=menu.addAction(tr("language.export"));auto action=menu.exec(languageFiles->mapToGlobal(QPoint(0,languageFiles->height())));if(action==load)importPack();else if(action==save)exportPack();});
        setStyleSheet(R"(
            QWidget#LauncherRoot { background:#090909; color:#eae7df; }
            QWidget#ControlPanel { background:#111111; border-left:1px solid #353431; }
            QLabel { color:#eeebe3; background:transparent; }
            QLabel#Title { font-size:37px; font-weight:800; }
            QLabel#Sub { color:#b4b1a9; font-size:13px; }
            QLabel#Eyebrow { color:#bcb8ae; font-family:Consolas; font-size:12px; font-weight:700; }
            QLabel#Badge { border:1px solid #4f4d47; padding:6px 9px; font-family:Consolas; font-size:12px; }
            QPushButton { background:#181818; color:#eae7df; border:1px solid #484641; padding:8px 14px; font-weight:600; }
            QPushButton:hover { background:#262522; border-color:#959084; }
            QPushButton:focus, QComboBox:focus, QCheckBox:focus { border:1px solid #eeeae1; }
            QPushButton:disabled { background:#151515; color:#77736d; border-color:#2e2d2a; }
            QPushButton#Primary { background:#ece9e0; color:#111111; border:1px solid #ece9e0; font-size:15px; font-weight:800; }
            QPushButton#Primary:hover { background:#ffffff; }
            QPushButton#Primary:focus { border:2px solid #817b6d; }
            QPushButton#Ghost { background:transparent; padding:6px 9px; font-size:12px; }
            QPushButton#Ghost:hover { background:#262522; }
            QPushButton#IconButton { padding:0; font-size:20px; }
            QComboBox, QLineEdit { color:#eae7df; background:#181818; border:1px solid #484641; padding:7px 10px; }
            QComboBox QAbstractItemView { background:#181818; color:#eeeae1; selection-background-color:#3d3b36; }
            QCheckBox { color:#e0ddd3; spacing:10px; font-size:13px; }
            QProgressBar { border:none; background:#363530; height:6px; }
            QProgressBar::chunk { background:#eeeae1; }
            QPlainTextEdit { color:#c4c0b5; background:#0b0b0b; border:1px solid #484641; font-family:Consolas; font-size:12px; }
            QMenu { background:#181818; color:#eeeae1; border:1px solid #484641; padding:4px; }
            QMenu::item { padding:8px 14px; } QMenu::item:selected { background:#3d3b36; }
        )");
        applyText();pages->setCurrentWidget(version.isEmpty()?setup:home);
    }

    QString tr(const QString &key) const {
        if(language=="custom"&&custom.contains(key))return custom[key].toString();
        for(const auto &t:texts)if(key==QLatin1String(t.key))return QString::fromUtf8(language=="ru"?t.ru:t.en);
        return key;
    }
    QString formatted(const QString &key) const {return tr(key).replace("{version}",version).replace("{path}",target);}
    QLabel *label(const char *key, const char *name="Sub") {auto l=new QLabel;l->setObjectName(name);l->setWordWrap(true);labels.append({l,key});return l;}
    QPushButton *button(const char *key,const char *name="",QWidget *parent=nullptr){auto b=new QPushButton(parent);b->setObjectName(name);buttons.append({b,key});return b;}
    QVBoxLayout *page(QWidget *&w){w=new QWidget;pages->addWidget(w);auto v=new QVBoxLayout(w);v->setContentsMargins(0,9,0,0);v->setSpacing(14);return v;}
    void buildHome(){
        auto v=page(home);v->addSpacing(20);v->addWidget(label("home.ready","Title"));
        auto row=new QHBoxLayout;installed=new QLabel;installed->setObjectName("Badge");newVersion=new QLabel;newVersion->setObjectName("Badge");row->addWidget(installed);row->addWidget(newVersion);row->addStretch();v->addLayout(row);
        v->addSpacing(14);v->addWidget(label("home.location","Eyebrow"));
        location=new QLabel(target);location->setWordWrap(true);location->setObjectName("Sub");location->setTextInteractionFlags(Qt::TextSelectableByMouse);v->addWidget(location);v->addStretch();
        status=new QLabel;status->setWordWrap(true);status->setObjectName("Sub");v->addWidget(status);
        auto play=button("button.launch","Primary");play->setMinimumHeight(54);v->addWidget(play);connect(play,&QPushButton::clicked,this,[this]{send("launch");});
        updateButton=new QPushButton;updateButton->setMinimumHeight(46);v->addWidget(updateButton);connect(updateButton,&QPushButton::clicked,this,[this]{start("update");});
        auto folders=new QHBoxLayout;auto app=button("button.app_folder","Ghost"),data=button("button.data_folder","Ghost");folders->addWidget(app);folders->addWidget(data);v->addLayout(folders);
        connect(app,&QPushButton::clicked,this,[this]{QDesktopServices::openUrl(QUrl::fromLocalFile(target));});connect(data,&QPushButton::clicked,this,[this]{QDesktopServices::openUrl(QUrl::fromLocalFile(dataPath));});
        auto manage=new QHBoxLayout;auto reinstall=button("button.reinstall","Ghost"),uninstall=button("button.uninstall","Ghost");manage->addWidget(reinstall);manage->addWidget(uninstall);v->addLayout(manage);
        connect(reinstall,&QPushButton::clicked,this,[this]{pages->setCurrentWidget(setup);});
        connect(uninstall,&QPushButton::clicked,this,[this]{QMessageBox box(QMessageBox::Question,"ECHOES",tr("uninstall.question"),QMessageBox::NoButton,this);auto yes=box.addButton(tr("dialog.yes"),QMessageBox::AcceptRole);box.addButton(tr("dialog.no"),QMessageBox::RejectRole);box.exec();if(box.clickedButton()==yes)send("uninstall");});
    }
    void buildSetup(){
        auto v=page(setup);v->setSpacing(11);v->addWidget(label("setup.title","Title"));v->addWidget(label("setup.subtitle"));v->addSpacing(4);v->addWidget(label("setup.location","Eyebrow"));
        auto row=new QHBoxLayout;directory=new QLineEdit(target);directory->setReadOnly(true);row->addWidget(directory,1);auto choose=button("button.change");row->addWidget(choose);v->addLayout(row);
        connect(choose,&QPushButton::clicked,this,[this]{auto path=QFileDialog::getExistingDirectory(this,tr("setup.choose"),directory->text());if(!path.isEmpty()){directory->setText(QDir(path).filePath("ECHOES"));applyText();}});
        space=new QLabel;space->setObjectName("Sub");v->addWidget(space);v->addWidget(label("setup.options","Eyebrow"));
        const char *keys[]={"desktop","menu","spotify","autostart","launch"};
        for(auto key:keys){auto check=new QCheckBox;const QString id=key;check->setChecked(store.value("opt_"+id,id!="autostart" && id!="spotify").toBool());options[id]=check;v->addWidget(check);}
        v->addStretch();auto bottom=new QHBoxLayout;back=button("button.back","Ghost");bottom->addWidget(back);auto install=button("button.install","Primary");install->setMinimumHeight(52);bottom->addWidget(install,1);v->addLayout(bottom);
        connect(back,&QPushButton::clicked,this,[this]{pages->setCurrentWidget(home);});connect(install,&QPushButton::clicked,this,[this]{start("install");});
    }
    void buildProgress(){
        auto v=page(progressPage);v->addSpacing(24);progressTitle=new QLabel;progressTitle->setObjectName("Title");progressTitle->setWordWrap(true);v->addWidget(progressTitle);v->addStretch();
        progressLabel=new QLabel;progressLabel->setWordWrap(true);v->addWidget(progressLabel);progressPercent=new QLabel;progressPercent->setObjectName("Eyebrow");v->addWidget(progressPercent);bar=new QProgressBar;bar->setTextVisible(false);v->addWidget(bar);
        details=button("button.details","Ghost");v->addWidget(details);log=new QPlainTextEdit;log->setReadOnly(true);log->setMaximumBlockCount(1500);log->setMinimumHeight(180);log->hide();v->addWidget(log);v->addStretch();
        connect(details,&QPushButton::clicked,this,[this]{log->setVisible(!log->isVisible());});
        retry=button("button.back");retry->hide();v->addWidget(retry);connect(retry,&QPushButton::clicked,this,[this]{pages->setCurrentWidget(version.isEmpty()?setup:home);});
    }
    void buildDone(){
        auto v=page(donePage);v->addStretch();
        doneTitle=new QLabel;doneTitle->setObjectName("Title");doneTitle->setWordWrap(true);doneTitle->setAlignment(Qt::AlignCenter);v->addWidget(doneTitle);v->addStretch();
        auto row=new QHBoxLayout;auto homeButton=button("button.home");row->addWidget(homeButton);auto play=button("button.launch","Primary");play->setMinimumHeight(52);row->addWidget(play,1);v->addLayout(row);
        connect(homeButton,&QPushButton::clicked,this,[this]{send("refresh");pages->setCurrentWidget(home);});connect(play,&QPushButton::clicked,this,[this]{send("launch");});
    }
    void applyText(){
        for(const auto &pair:labels)pair.first->setText(tr(pair.second));
        for(const auto &pair:buttons)pair.first->setText(tr(pair.second));
        for(auto it=options.begin();it!=options.end();++it)it.value()->setText(tr("option."+it.key()));
        brand->platform=tr("brand.platform");brand->update();
        launcherLabel->setText(tr("header.launcher"));languages->setAccessibleName(tr("language.label"));languageFiles->setToolTip(tr("language.manage"));languageFiles->setAccessibleName(tr("language.manage"));
        installed->setText(formatted("home.installed"));newVersion->setText(tr("home.new").replace("{version}",remote));newVersion->setVisible(newer);
        updateButton->setText(tr("button.update").replace("{version}",remote));updateButton->setVisible(newer);location->setText(target);back->setVisible(!version.isEmpty());
        status->setText(tr(statusKey));progressTitle->setText(tr(mode=="update"?"progress.update":"progress.install"));progressLabel->setText(tr(stage));updatePercentage();doneTitle->setText(tr(mode=="update"?"done.update":"done.install"));
        QString disk=directory->text();
        while(!QFileInfo::exists(disk)){
            const auto parent=QFileInfo(disk).dir().absolutePath();
            if(parent==disk)break;
            disk=parent;
        }
        QStorageInfo storage(disk);
        space->setText(storage.isValid() ? tr("setup.space").replace("{space}",QString::number(qMax<qint64>(0,storage.bytesAvailable())/double(1LL<<30),'f',1)) : tr("setup.space_unknown"));
    }
    void start(const QString &op){
        if(busy)return;mode=op;busy=true;stage="progress.download";bar->setRange(0,100);bar->setValue(0);log->clear();log->hide();retry->hide();pages->setCurrentWidget(progressPage);applyText();
        if(op=="install")target=directory->text();
        QJsonObject o;for(auto it=options.begin();it!=options.end();++it){o[it.key()]=it.value()->isChecked();store.setValue("opt_"+it.key(),it.value()->isChecked());}
        send(op,o);
    }
    void send(const QString &action,QJsonObject extra={}){
        extra["action"]=action;extra["target"]=target;extra["language"]=language=="ru"?"ru":"en";
        if(callback){auto data=QJsonDocument(extra).toJson(QJsonDocument::Compact);callback(data.constData());}
    }
    void setState(const QJsonObject &s){
        if(s.contains("target")){target=s["target"].toString();store.setValue("installation",target);directory->setText(target);}
        if(s.contains("version"))version=s["version"].toString();
        if(s.contains("remote"))remote=s["remote"].toString();
        newer=isNewer(remote,version);
        if(s.contains("remote")||statusKey=="home.latest"||statusKey.isEmpty())
            statusKey=remote.isEmpty()?"home.offline":newer?QString():"home.latest";
        if(s.contains("status"))statusKey=s["status"].toString();
        applyText();
        if(s.contains("status")&&statusKey.startsWith("error."))QMessageBox::warning(this,tr("error.title"),tr(statusKey));
    }
    void progress(int pct,const QJsonObject &event){
        if(pct>=0){bar->setRange(0,100);bar->setValue(qBound(0,pct,100));}else if(pct==-1)bar->setRange(0,0);
        if(event.contains("stage"))stage=event["stage"].toString();
        if(event.contains("line"))log->appendPlainText(event["line"].toString());
        progressLabel->setText(tr(stage));
        updatePercentage();
    }
    void updatePercentage() {
        progressPercent->setVisible(bar->maximum() > 0 && busy);
        progressPercent->setText(tr("progress.complete").replace("{percent}", QString::number(bar->value())));
    }
    void done(bool success,const QString &error){
        busy=false;bar->setRange(0,100);bar->setValue(success?100:0);updatePercentage();
        if(success){pages->setCurrentWidget(donePage);applyText();}else{stage=error.isEmpty()?"error.backend":error;progressLabel->setText(tr(stage));log->show();retry->show();}
    }
    bool loadPack(const QByteArray &bytes,bool persist){
        QJsonObject parsed;QString name;if(!parsePack(bytes,parsed,name))return false;
        custom=parsed;customName=name;language="custom";
        if(persist){store.setValue("translation_pack",bytes);store.setValue("language",language);}
        int index=languages->findData("custom");languages->blockSignals(true);
        if(index<0){languages->addItem(name,"custom");index=languages->count()-1;}else languages->setItemText(index,name);
        languages->setCurrentIndex(index);languages->blockSignals(false);applyText();return true;
    }
    void importPack(){
        auto path=QFileDialog::getOpenFileName(this,tr("language.import"),QString(),"JSON (*.json)");if(path.isEmpty())return;
        QFile f(path);if(!f.open(QIODevice::ReadOnly)||!loadPack(f.read(256*1024+1),true)){QMessageBox::warning(this,"ECHOES",tr("language.invalid"));return;}
        QMessageBox::information(this,"ECHOES",tr("language.loaded"));
    }
    void exportPack(){
        auto path=QFileDialog::getSaveFileName(this,tr("language.export"),"echoes-launcher.en.json","JSON (*.json)");if(path.isEmpty())return;
        QFile f(path);QJsonObject obj{{"format",1},{"name","My language"},{"translations",english()}};
        if(!f.open(QIODevice::WriteOnly)||f.write(QJsonDocument(obj).toJson())<0)QMessageBox::warning(this,"ECHOES",tr("language.save_error"));
    }
protected:
    void closeEvent(QCloseEvent *e) override {if(busy){QMessageBox::information(this,"ECHOES",tr("error.busy"));e->ignore();}else QWidget::closeEvent(e);}
private:
    QSettings store;
    QString language,customName,target,version,remote,dataPath,mode="install",stage="progress.download",statusKey="home.checking";
    QJsonObject custom;bool busy=false,newer=false;
    Brand *brand;QStackedWidget *pages;QWidget *home,*setup,*progressPage,*donePage;
    QComboBox *languages;QPushButton *languageFiles,*updateButton,*back,*details,*retry;
    QLabel *launcherLabel,*installed,*newVersion,*location,*status,*space,*progressTitle,*progressLabel,*progressPercent,*doneTitle;
    QLineEdit *directory;QProgressBar *bar;QPlainTextEdit *log;
    QMap<QString,QCheckBox*> options;
    QVector<QPair<QLabel*,QString>> labels;QVector<QPair<QPushButton*,QString>> buttons;
};

API const char *ela_qt_version(){return QT_VERSION_STR;}
API void ela_callback(Callback cb){callback=cb;}
API void *ela_new(const char *json){return new Launcher(QJsonDocument::fromJson(json).object());}
API void ela_state(void *p,const char *json){static_cast<Launcher*>(p)->setState(QJsonDocument::fromJson(json).object());}
API void ela_progress(void *p,int pct,const char *json){static_cast<Launcher*>(p)->progress(pct,QJsonDocument::fromJson(json).object());}
API void ela_done(void *p,int ok,const char *error){static_cast<Launcher*>(p)->done(ok!=0,QString::fromUtf8(error));}
API int ela_validate_pack(const char *json){QJsonObject result;QString name;return parsePack(QByteArray(json),result,name)?1:0;}
API int ela_load_pack(void *p,const char *json,int persist){return static_cast<Launcher*>(p)->loadPack(json,persist!=0)?1:0;}
API const char *ela_english_template(){static QByteArray bytes=QJsonDocument(QJsonObject{{"format",1},{"name","My language"},{"translations",english()}}).toJson();return bytes.constData();}
