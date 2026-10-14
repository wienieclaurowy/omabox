import QtQuick
import QtQuick.Effects
import qs.Commons
import qs.Commons as Commons
import qs.Ui
import "Model.js" as Model

// One post at a time: header, then the body in its own scroller with a reading-progress hairline.
Column {
  id: root

  property var panel: null
  property var item: null
  property alias flick: flick
  // Height the panel can give the whole reader, header included.
  property real maxHeight: 1e6

  readonly property string tag: item && panel ? Model.versionTag(item, panel.feedState.installed) : ""
  // X posts: author header like the original (avatar, name, @handle) instead of the source meta line.
  readonly property var profile: item && panel && item.short && panel.feedState.profiles
    ? (panel.feedState.profiles[item.source] || null) : null
  // A repost's header names the original author; the source account moves to a "reposted" line above it.
  // repost_avatar arrives with the comments (bin/omabox load_replies).
  readonly property var repost: profile && item.repost ? item.repost : null
  readonly property string authorAvatar: repost ? (item.repost_avatar ? panel.imageDir + "/" + item.repost_avatar : "")
    : (profile && profile.avatar ? profile.avatar : "")
  readonly property bool isPost: item !== null && !item.note
  readonly property bool picking: isPost && panel !== null && panel.snoozePickerId === item.id
  readonly property bool articleAvailable: isPost && panel !== null && panel.view === "feed"
    && Model.articleAvailable(item, panel.feedState.profiles)
  readonly property bool loadingArticle: isPost && panel !== null && panel.articleLoadingId === item.id
  readonly property bool showingFull: isPost && item.showingFull === true
  readonly property color buttonColor: panel ? panel.fg : Commons.Color.foreground
  readonly property string buttonFont: panel ? panel.fontFamily : Style.font.family
  readonly property real progress: flick.contentHeight > flick.height
    ? Math.max(0, Math.min(1, flick.contentY / (flick.contentHeight - flick.height))) : 1

  spacing: Style.space(6)

  // Every picture and video poster in the body as { rect, media } (Model.mediaAt), in document order, redone after each
  // relayout; clicks, i and the play badges read it. Not counted per click with getText(0, q): once q sits in a table
  // (comments, quote cards) that range grows to the whole cell and counts one object too many.
  property var mediaObjects: []
  readonly property var videoBadges: mediaObjects.filter(function(object) { return object.media.kind === "video" })

  function placeMedia() {
    var objects = []
    var text = item ? body.getText(0, body.length) : ""
    var object = -1
    for (var q = text.indexOf("\uFFFC"); q >= 0; q = text.indexOf("\uFFFC", q + 1)) {
      var media = Model.mediaAt(item.html, ++object)
      if (!media) continue
      var from = body.positionToRectangle(q)
      var to = body.positionToRectangle(q + 1)
      objects.push({ rect: Qt.rect(from.x, from.y, (to.y === from.y ? to.x : body.width) - from.x, from.height), media: media })
    }
    mediaObjects = objects
  }

  function mediaAtPoint(x, y) {
    for (var i = 0; i < mediaObjects.length; i++) {
      var rect = mediaObjects[i].rect
      if (x >= rect.x && x <= rect.x + rect.width && y >= rect.y && y <= rect.y + rect.height) return mediaObjects[i].media
    }
    return null
  }

  // Media for i: the first picture or video not yet half scrolled past, else the last one, so the one on screen opens.
  function nearestMedia() {
    var top = flick.contentY - body.y
    for (var i = 0; i < mediaObjects.length; i++) {
      var rect = mediaObjects[i].rect
      if (rect.y + rect.height / 2 > top) return mediaObjects[i].media
    }
    return mediaObjects.length > 0 ? mediaObjects[mediaObjects.length - 1].media : null
  }

  // Content y of the next (direction 1) or previous (-1) section heading relative to the scroll position, or -1.
  // Headings are found by their label text in the rendered document, in order, so repeated labels resolve in sequence.
  function sectionTarget(direction) {
    if (!item) return -1
    var labels = Model.headingLabels(item.html)
    var plain = body.getText(0, body.length).toLowerCase()
    var offsets = []
    var from = 0
    for (var i = 0; i < labels.length; i++) {
      var at = plain.indexOf(labels[i].toLowerCase(), from)
      if (at < 0) continue
      offsets.push(Math.max(0, body.y + body.positionToRectangle(at).y - Style.space(8)))
      from = at + labels[i].length
    }
    var y = flick.contentY
    var slack = Style.space(4)
    if (direction > 0) {
      for (var j = 0; j < offsets.length; j++) if (offsets[j] > y + slack) return offsets[j]
    } else {
      for (var k = offsets.length - 1; k >= 0; k--) if (offsets[k] < y - slack) return offsets[k]
      return y > slack ? 0 : -1
    }
    return -1
  }

  Item {
    width: parent.width
    height: Math.max(backLabel.implicitHeight, openButton.height)

    Text {
      id: backLabel
      anchors.verticalCenter: parent.verticalCenter
      textFormat: Text.PlainText
      text: "‹  " + (root.item && root.item.note ? Tr.t("reader.backNotifications") : Tr.t("reader.backFeed"))
      color: backMouse.containsMouse ? Commons.Color.accent : (root.panel ? root.panel.dim : Commons.Color.foreground)
      font.family: root.panel ? root.panel.fontFamily : Style.font.family
      font.pixelSize: Style.font.caption
      font.letterSpacing: 1.2
      font.bold: true

      MouseArea {
        id: backMouse
        anchors.fill: parent
        anchors.margins: -Style.space(6)
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: root.panel.closeReader()
      }
    }

    ChoicePicker {
      visible: root.picking
      choices: Model.snoozeChoices(Tr)
      anchors.right: parent.right
      anchors.verticalCenter: parent.verticalCenter
      foreground: root.buttonColor
      dim: root.panel ? root.panel.faint : Commons.Color.foreground
      fontFamily: root.buttonFont
      onPicked: function(choice) { root.panel.snoozeItem(root.item, choice) }
      onCancelled: root.panel.closeSnooze()
    }

    Row {
      visible: !root.picking
      anchors.right: parent.right
      anchors.verticalCenter: parent.verticalCenter
      spacing: Style.space(6)

      Text {
        anchors.verticalCenter: parent.verticalCenter
        textFormat: Text.PlainText
        text: root.panel ? Model.fill(Tr.t("reader.position"), [Tr.formatNumber(root.panel.cursor + 1), Tr.formatNumber(root.panel.rows.length)]) : ""
        color: root.panel ? root.panel.faint : Commons.Color.foreground
        font.family: root.panel ? root.panel.fontFamily : Style.font.family
        font.pixelSize: Style.font.caption
      }

      PanelActionButton {
        iconText: "󰅁"
        tooltipText: Tr.t("actions.previous")
        enabled: root.panel !== null && root.panel.cursor > 0
        foreground: root.buttonColor
        fontFamily: root.buttonFont
        onClicked: root.panel.stepReader(-1)
      }

      PanelActionButton {
        iconText: "󰅂"
        tooltipText: Tr.t("actions.next")
        enabled: root.panel !== null && root.panel.cursor < root.panel.rows.length - 1
        foreground: root.buttonColor
        fontFamily: root.buttonFont
        onClicked: root.panel.stepReader(1)
      }

      PanelActionButton {
        readonly property bool pictures: root.isPost && root.panel !== null && Model.imagePaths(root.item.html, root.panel.imageDir).length > 0
        readonly property bool videos: root.isPost && Model.videoUrls(root.item.html).length > 0
        visible: pictures || videos
        iconText: pictures ? "󰋩" : "󰕧"
        tooltipText: pictures && videos ? Tr.t("actions.picturesAndVideos") : pictures ? Tr.t("actions.pictures") : Tr.t("actions.playVideo")
        foreground: root.buttonColor
        fontFamily: root.buttonFont
        onClicked: root.panel.openMedia()
      }

      PanelActionButton {
        visible: root.articleAvailable
        enabled: !root.loadingArticle
        iconText: String.fromCodePoint(root.loadingArticle ? 0xF051F : 0xF0395)
        tooltipText: root.loadingArticle ? Tr.t("reader.fetchingArticle") : root.showingFull ? Tr.t("actions.feedVersion") : Tr.t("actions.fullArticle")
        foreground: root.showingFull ? Commons.Color.accent : root.buttonColor
        fontFamily: root.buttonFont
        onClicked: root.panel.toggleArticle()
      }

      PanelActionButton {
        visible: root.isPost
        iconText: root.isPost && root.item.later === true ? "󰃀" : "󰃃"
        tooltipText: root.isPost && root.item.later === true ? Tr.t("actions.unmarkLater") : Tr.t("actions.readLater")
        foreground: root.isPost && root.item.later === true ? Commons.Color.accent : root.buttonColor
        fontFamily: root.buttonFont
        onClicked: root.panel.toggleLaterCurrent()
      }

      PanelActionButton {
        visible: root.isPost
        iconText: "󰒲"
        tooltipText: Tr.t("actions.snooze")
        foreground: root.buttonColor
        fontFamily: root.buttonFont
        onClicked: root.panel.openSnooze()
      }

      PanelActionButton {
        visible: root.tag === "newer"
        iconText: "󰚰"
        tooltipText: Tr.t("actions.updateOmarchy")
        foreground: Commons.Color.accent
        fontFamily: root.buttonFont
        onClicked: root.panel.runUpdate()
      }

      PanelActionButton {
        visible: root.item !== null && (root.isPost ? !!root.item.link : true)
        iconText: "󰆏"
        tooltipText: root.isPost ? Tr.t("actions.copyLink") : Tr.t("actions.copyMessage")
        foreground: root.buttonColor
        fontFamily: root.buttonFont
        onClicked: root.isPost ? root.panel.copyLink() : root.panel.copyNotification(root.panel.cursor)
      }

      PanelActionButton {
        visible: root.item !== null && !root.isPost && root.panel !== null
          && Model.notificationArgv(root.panel.noteRows[root.panel.cursor]) !== null
        iconText: "󰐊"
        tooltipText: Tr.t("actions.runAction")
        foreground: root.buttonColor
        fontFamily: root.buttonFont
        onClicked: root.panel.runNotificationAction(root.panel.cursor)
      }

      PanelActionButton {
        id: openButton
        visible: root.isPost && !!root.item.link
        iconText: "󰏌"
        tooltipText: Tr.t("actions.openInBrowser")
        foreground: root.buttonColor
        fontFamily: root.buttonFont
        onClicked: root.panel.openLink(root.panel.cursor)
      }
    }
  }

  Text {
    visible: root.repost !== null
    topPadding: Style.space(6)
    leftPadding: Style.space(50)
    textFormat: Text.PlainText
    text: root.repost ? "󰑖  " + Model.fill(Tr.t("reader.reposted"), [root.profile.name]) : ""
    color: root.panel ? root.panel.dim : Commons.Color.foreground
    font.family: root.panel ? root.panel.fontFamily : Style.font.family
    font.pixelSize: Style.font.caption
  }

  Row {
    visible: root.profile !== null
    topPadding: root.repost ? 0 : Style.space(6)
    spacing: Style.space(10)

    Item {
      width: Style.space(40)
      height: width
      anchors.verticalCenter: parent.verticalCenter

      Image {
        id: avatar
        anchors.fill: parent
        visible: false
        source: root.authorAvatar ? "file://" + root.authorAvatar : ""
        sourceSize.width: Math.ceil(width * 2)
        sourceSize.height: Math.ceil(height * 2)
        fillMode: Image.PreserveAspectCrop
        smooth: true
        asynchronous: true
      }

      Rectangle {
        id: avatarMask
        anchors.fill: parent
        radius: width / 2
        visible: false
        layer.enabled: true
      }

      MultiEffect {
        anchors.fill: parent
        source: avatar
        visible: avatar.status === Image.Ready
        maskEnabled: true
        maskSource: avatarMask
      }

      Rectangle {
        anchors.fill: parent
        visible: avatar.status !== Image.Ready
        radius: width / 2
        color: root.panel ? Util.alpha(root.panel.fg, 0.12) : "transparent"
      }
    }

    Column {
      anchors.verticalCenter: parent.verticalCenter
      spacing: Style.space(2)

      Text {
        textFormat: Text.PlainText
        text: root.repost ? root.repost.name : root.profile ? root.profile.name : ""
        color: root.panel ? root.panel.fg : Commons.Color.foreground
        font.family: root.panel ? root.panel.readingFont : Style.font.family
        font.styleName: "Bold"
        font.pixelSize: Style.font.title
      }

      Text {
        textFormat: Text.PlainText
        text: root.profile && root.item
          ? [root.repost ? (root.repost.handle ? "@" + root.repost.handle : "") : "@" + root.profile.handle,
              new Date(root.item.published).toLocaleString(Tr.locale, Tr.t("time.stampYear"))]
            .filter(function(part) { return part !== "" }).join("  ·  ")
          : ""
        color: root.panel ? root.panel.dim : Commons.Color.foreground
        font.family: root.panel ? root.panel.fontFamily : Style.font.family
        font.pixelSize: Style.font.caption
      }
    }
  }

  // The source name gives way (elides) so the date, reading time and tags stay on the line.
  Row {
    id: metaRow
    visible: root.profile === null
    topPadding: Style.space(6)
    spacing: Style.space(8)
    readonly property real fixedWidth: {
      var width = 0, shown = 0
      for (var i = 0; i < children.length; i++) {
        if (!children[i].visible) continue
        shown++
        if (children[i] !== sourceLabel) width += children[i].width
      }
      return width + spacing * Math.max(0, shown - 1)
    }

    SourceIcon {
      anchors.verticalCenter: parent.verticalCenter
      icon: root.item && root.item.icon ? root.item.icon
        : (root.item && root.panel && root.panel.feedState.icons ? (root.panel.feedState.icons[root.item.source] || {}) : ({}))
      color: root.panel ? root.panel.dim : Commons.Color.foreground
      fontFamily: root.panel ? root.panel.fontFamily : Style.font.family
      size: Style.font.body
    }

    Text {
      id: sourceLabel
      anchors.verticalCenter: parent.verticalCenter
      width: Math.min(implicitWidth, Math.max(Style.space(40), root.width - metaRow.fixedWidth))
      textFormat: Text.PlainText
      elide: Text.ElideRight
      text: root.item ? String(root.item.source || "").toUpperCase() : ""
      color: root.panel ? root.panel.dim : Commons.Color.foreground
      font.family: root.panel ? root.panel.fontFamily : Style.font.family
      font.pixelSize: Style.font.caption
      font.letterSpacing: 1
      font.bold: true
    }

    Text {
      anchors.verticalCenter: parent.verticalCenter
      textFormat: Text.PlainText
      text: root.item && root.panel
        ? [new Date(root.item.published).toLocaleString(Tr.locale, root.item.note ? Tr.t("time.stampYear") : Tr.t("time.dateYear")),
            Model.readingTime(root.item, Tr)]
          .filter(function(part) { return part !== "" }).map(function(part) { return "·  " + part }).join("  ").toUpperCase()
        : ""
      color: root.panel ? root.panel.dim : Commons.Color.foreground
      font.family: root.panel ? root.panel.fontFamily : Style.font.family
      font.pixelSize: Style.font.caption
      font.letterSpacing: 1
      font.bold: true
    }

    Text {
      visible: root.tag !== ""
      anchors.verticalCenter: parent.verticalCenter
      textFormat: Text.PlainText
      text: "·  " + (root.tag === "newer" ? Tr.t("feed.newerTag") : Tr.t("feed.installedTag"))
      color: root.tag === "newer" ? Commons.Color.accent : (root.panel ? root.panel.dim : Commons.Color.foreground)
      font.family: root.panel ? root.panel.fontFamily : Style.font.family
      font.pixelSize: Style.font.caption
      font.letterSpacing: 1
      font.bold: true
    }

    Text {
      visible: root.showingFull
      anchors.verticalCenter: parent.verticalCenter
      textFormat: Text.PlainText
      text: "·  " + Tr.t("reader.fullArticleTag")
      color: Commons.Color.accent
      font.family: root.panel ? root.panel.fontFamily : Style.font.family
      font.pixelSize: Style.font.caption
      font.letterSpacing: 1
      font.bold: true
    }
  }

  // Short posts (X, Mastodon) have no real title: the body is the post, a heading would repeat it.
  Text {
    visible: root.item !== null && root.item.short !== true
    width: parent.width
    textFormat: Text.PlainText
    wrapMode: Text.WordWrap
    text: root.item ? root.item.title : ""
    color: root.panel ? root.panel.fg : Commons.Color.foreground
    font.family: root.panel ? root.panel.readingFont : Style.font.family
    font.styleName: "Bold"
    font.pixelSize: Style.font.display
    lineHeight: 1.1
  }

  Text {
    visible: root.item !== null && (root.item.summary || "") !== ""
    width: parent.width
    textFormat: Text.PlainText
    wrapMode: Text.WordWrap
    text: root.item ? root.item.summary || "" : ""
    color: root.panel ? root.panel.dim : Commons.Color.foreground
    font.family: root.panel ? root.panel.fontFamily : Style.font.family
    font.pixelSize: Style.font.caption
    font.letterSpacing: 0.5
  }

  Item {
    width: parent.width
    height: Style.space(6)
  }

  Item {
    width: parent.width
    height: Style.spacing.hairline

    Rectangle {
      anchors.fill: parent
      color: root.panel ? root.panel.fg : Commons.Color.foreground
      opacity: 0.12
    }

    Rectangle {
      width: Math.round(parent.width * root.progress)
      height: parent.height
      color: Commons.Color.accent

      Behavior on width { NumberAnimation { duration: 140; easing.type: Easing.OutCubic } }
    }
  }

  Flickable {
    id: flick
    width: parent.width
    height: Math.min(Style.space(620), contentHeight, Math.max(Style.space(120), root.maxHeight - flick.y))
    contentWidth: width
    contentHeight: body.implicitHeight + Style.space(28)
    clip: true
    boundsBehavior: Flickable.StopAtBounds

    // html is rebuilt from an allowlist by bin/omabox; its only <img> are omabox-img:/omabox-avatar: cache refs (Model.renderHtml).
    // TextEdit, not Text: positionToRectangle/getText locate headings for ]/[. It must never take focus
    // (the panel's key layer holds it), hence readOnly, no mouse selection and no focus on press.
    TextEdit {
      id: body
      y: Style.space(14)
      width: flick.width
      readOnly: true
      selectByMouse: false
      activeFocusOnPress: false
      textFormat: TextEdit.RichText
      wrapMode: TextEdit.Wrap
      // Kept while the picture viewer or video player hides the panel: an emptied body clamps the scroll to the top.
      text: root.item && root.panel && (root.visible || root.panel.viewingMedia)
        ? root.panel.readerCss + Model.renderHtml(root.item.html, root.panel.imageDir, width, root.panel.commentFaces)
        : ""
      color: root.panel ? root.panel.fg : Commons.Color.foreground
      font.family: root.panel ? root.panel.readingFont : Style.font.family
      font.styleName: "Regular"
      font.pixelSize: root.panel ? root.panel.readerFontSize : Style.font.title
      onTextChanged: Qt.callLater(root.placeMedia)
      onContentSizeChanged: Qt.callLater(root.placeMedia)
      // Clicks are handled here, not by onLinkActivated: most pictures sit inside link cards and video posters inside
      // links to their files, and a click on either must open the viewer or player only, not the link as well.
      TapHandler {
        onTapped: function(eventPoint) {
          var p = eventPoint.position
          var media = root.mediaAtPoint(p.x, p.y)
          if (media) {
            root.panel.openMedia(media)
            return
          }
          var link = Model.webLink(body.linkAt(p.x, p.y))
          if (link !== "") Qt.openUrlExternally(link)
        }
      }

      HoverHandler {
        id: bodyHover
        cursorShape: parent.hoveredLink !== "" || root.mediaAtPoint(bodyHover.point.position.x, bodyHover.point.position.y) !== null
          ? Qt.PointingHandCursor : Qt.ArrowCursor
      }
    }

    // No pointer handler that takes presses: a click falls through to the body's TapHandler, which plays the video.
    Repeater {
      model: root.videoBadges

      Rectangle {
        required property var modelData
        readonly property bool opening: root.panel !== null && root.item !== null
          && root.panel.openingVideo === root.item.id + ":" + modelData.media.index
        x: body.x + modelData.rect.x + (modelData.rect.width - width) / 2
        y: body.y + modelData.rect.y + (modelData.rect.height - height) / 2
        width: Style.space(52)
        height: width
        radius: width / 2
        color: Util.alpha(root.panel ? root.panel.cardColor : Commons.Color.popups.background, 0.92)

        HoverHandler { id: badgeHover }

        Text {
          anchors.centerIn: parent
          // the play triangle's visual centre sits right of its box centre
          anchors.horizontalCenterOffset: parent.opening ? 0 : Style.space(2)
          textFormat: Text.PlainText
          text: String.fromCodePoint(parent.opening ? 0xF051F : 0xF040A)
          color: badgeHover.hovered || parent.opening ? Commons.Color.accent : (root.panel ? root.panel.fg : Commons.Color.foreground)
          font.family: root.panel ? root.panel.fontFamily : Style.font.family
          font.pixelSize: Math.round(parent.width * 0.55)
        }
      }
    }
  }
}
