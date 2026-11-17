import QtQuick
import Quickshell
import qs.Commons
import qs.Commons as Commons
import qs.Ui
import "omakit"

Panel {
  id: root
  moduleName: "io.github.ekollof.omargb"
  manageIpc: false

  readonly property string omargbBin: Quickshell.env("HOME") + "/.local/bin/omargb"
  property bool busy: false
  property string taskKind: ""
  property string error: ""
  property bool enabled: true
  property string solid: ""
  property string strategy: "warmest"
  property string lamp: ""
  readonly property var strategies: ["warmest", "least_blue", "most_saturated", "coolest", "brightest"]
  property var devices: []
  property int selectedControl: 0

  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  Commons.Translations { id: strings; directory: Qt.resolvedUrl("i18n") }

  function open(payloadJson) {
    selectedControl = 0
    controller.show()
    if (!busy) startTask("plan", ["plan", "--json"], 20000)
  }

  function close() { controller.hide() }

  function controlCount() {
    var count = 3
    for (var i = 0; i < devices.length; i++) count += devices[i].gradient ? 2 : 1
    return count
  }

  function deviceControl(index) {
    var at = 2
    for (var i = 0; i < index && i < devices.length; i++) at += devices[i].gradient ? 2 : 1
    return at
  }

  function strategyText() {
    var name = strings.t("panel.strategy." + strategy)
    return lamp.length === 7 ? strings.t("panel.strategyDetail").arg(name).arg(lamp) : name
  }

  function startTask(kind, args, deadline) {
    if (busy) return
    taskKind = kind
    error = ""
    task.deadlineMs = deadline
    task.command = [omargbBin].concat(args)
    busy = true
    task.start()
  }

  function finished(result) {
    busy = false
    if (!result || result.state !== "ok") {
      var state = result && result.state ? result.state : "spawn-failed"
      var reason = result && result.reason ? result.reason : ""
      error = (state + (reason ? ": " + reason : "")).slice(0, 240)
      return
    }
    if (taskKind === "plan") {
      takePlan(result.stdout || "")
      return
    }
    if (taskKind === "paint") {
      startTask("apply", ["apply"], 45000)
      return
    }
    startTask("plan", ["plan", "--json"], 20000)
  }

  function takePlan(text) {
    var data
    try { data = JSON.parse(text) }
    catch (e) { error = "invalid"; return }
    if (!data || data.ok !== true || !Array.isArray(data.devices)) {
      error = data && typeof data.error === "string" ? data.error.slice(0, 200) : "invalid"
      return
    }
    enabled = data.enabled === true
    solid = typeof data.solid === "string" && data.solid.length === 7 ? data.solid : ""
    strategy = strategies.indexOf(data.strategy) >= 0 ? data.strategy : "warmest"
    lamp = typeof data.lamp === "string" && data.lamp.length === 7 ? data.lamp : ""
    var rows = []
    for (var i = 0; i < data.devices.length && rows.length < 32; i++) {
      var row = data.devices[i]
      if (!row || typeof row.bus !== "string" || typeof row.id !== "string" || typeof row.name !== "string") continue
      if (row.bus.length > 16 || row.id.length > 200 || row.name.length > 120) continue
      rows.push({
        bus: row.bus,
        id: row.id,
        name: row.name,
        effect: row.effect === "gradient" ? "gradient" : "solid",
        enabled: row.enabled !== false,
        gradient: row.gradient === true
      })
    }
    devices = rows
    if (selectedControl >= controlCount()) selectedControl = 0
  }

  function setMaster(value) {
    startTask(value ? "paint" : "config", ["config", "enabled", value ? "true" : "false"], 10000)
  }

  function cycleStrategy() {
    var at = strategies.indexOf(strategy)
    var next = strategies[(at + 1) % strategies.length]
    startTask("paint", ["config", "strategy", next], 10000)
  }

  function setDevice(index, value) {
    var row = devices[index]
    if (!row) return
    startTask(value ? "paint" : "config", ["config", "device", row.bus, row.id, "enabled", value ? "true" : "false"], 10000)
  }

  function setEffect(index, effect) {
    var row = devices[index]
    if (!row) return
    startTask("paint", ["config", "device", row.bus, row.id, "effect", effect], 10000)
  }

  function activate() {
    if (busy) return
    if (selectedControl === 0) { setMaster(!enabled); return }
    if (selectedControl === 1) { cycleStrategy(); return }
    var at = 2
    for (var i = 0; i < devices.length; i++) {
      if (selectedControl === at) { setDevice(i, !devices[i].enabled); return }
      at++
      if (devices[i].gradient) {
        if (selectedControl === at) {
          setEffect(i, devices[i].effect === "gradient" ? "solid" : "gradient")
          return
        }
        at++
      }
    }
    startTask("apply", ["apply"], 45000)
  }

  WidgetButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    text: "󰌵" // nf-md-lightbulb, one code point so the bar treats it as an icon
    active: root.opened || root.busy
    tooltipText: strings.t("bar.tooltip")
    onPressed: function(mouseButton) {
      if (mouseButton === Qt.LeftButton) root.toggle()
    }
  }

  KeyboardPanel {
    id: panel
    anchorItem: button
    owner: root
    bar: root.bar
    open: root.opened
    focusTarget: panel.loadedContent
    contentWidth: panel.fittedContentWidth(Style.space(360))
    contentHeight: panel.fittedContentHeight(panel.loadedContentHeight, Style.space(560))
    // The card stays at the cap and the host viewport scrolls the rest.
    // Its own scrollbar fades out at rest, so the thumb below stays painted
    // on the card for as long as the list overflows.
    scrollOverflow: true
    content: PanelKeyCatcher {
      id: keys
      implicitHeight: form.implicitHeight
      anchors.fill: parent
      onCloseRequested: root.close()
      onMoveRequested: function(dx, dy) {
        var count = root.controlCount()
        root.selectedControl = (root.selectedControl + (dy || dx) + count) % count
      }
      onTabRequested: function(direction) {
        var count = root.controlCount()
        root.selectedControl = (root.selectedControl + direction + count) % count
      }
      onActivateRequested: root.activate()

      Rectangle {
        id: thumb
        z: 20
        width: 4
        radius: 2
        color: Commons.Color.foreground
        opacity: 0.7
        visible: false
      }

      property bool thumbBound: false
      function placeThumb() {
        var item = parent
        var flick = null
        while (item) {
          if (item.visibleArea !== undefined && item.contentHeight !== undefined) {
            flick = item
            break
          }
          item = item.parent
        }
        if (!flick || !flick.parent) {
          thumb.visible = false
          return
        }
        if (!thumbBound) {
          thumbBound = true
          flick.contentYChanged.connect(placeThumb)
          flick.heightChanged.connect(placeThumb)
          flick.contentHeightChanged.connect(placeThumb)
        }
        var overflowing = flick.contentHeight > flick.height + 1
        thumb.visible = overflowing
        if (!overflowing) return
        if (thumb.parent !== flick.parent) thumb.parent = flick.parent
        var span = Math.max(1, flick.contentHeight - flick.height)
        var height = Math.max(36, flick.height * flick.height / flick.contentHeight)
        var travel = Math.max(1, flick.height - height)
        var origin = flick.mapToItem(flick.parent, 0, 0)
        thumb.height = height
        thumb.x = origin.x + flick.width - thumb.width - 4
        thumb.y = origin.y + (flick.contentY / span) * travel
      }
      Component.onCompleted: Qt.callLater(placeThumb)
      onImplicitHeightChanged: Qt.callLater(placeThumb)
      Column {
        id: form
        width: parent.width
        spacing: Style.spacing.sm
          Text {
            text: strings.t("panel.title")
            textFormat: Text.PlainText
            color: Commons.Color.foreground
            font.family: Style.font.family
            font.pixelSize: Style.font.subtitle
            font.bold: true
          }
          Text {
            width: parent.width
            visible: root.solid !== ""
            text: strings.t("panel.colour").arg(root.solid)
            textFormat: Text.PlainText
            color: Commons.Color.muted
            font.family: Style.font.family
            font.pixelSize: Style.font.caption
          }
          Text {
            width: parent.width
            visible: root.error !== ""
            text: root.error
            textFormat: Text.PlainText
            wrapMode: Text.Wrap
            color: Commons.Color.urgent
            font.family: Style.font.family
            font.pixelSize: Style.font.caption
          }
          Toggle {
            width: parent.width
            label: strings.t("panel.follow")
            description: root.enabled ? strings.t("panel.followOn") : strings.t("panel.followOff")
            checked: root.enabled
            enabled: !root.busy
            hasCursor: root.selectedControl === 0
            onClicked: root.setMaster(!root.enabled)
          }
          Button {
            width: parent.width
            text: root.strategyText()
            enabled: !root.busy
            hasCursor: root.selectedControl === 1
            onClicked: root.cycleStrategy()
          }
          Text {
            width: parent.width
            visible: root.devices.length === 0 && root.error === "" && !root.busy
            text: strings.t("panel.empty")
            textFormat: Text.PlainText
            color: Commons.Color.muted
            font.family: Style.font.family
            font.pixelSize: Style.font.body
          }
          Repeater {
            model: root.devices
            delegate: Item {
              id: device
              required property var modelData
              required property int index
              width: form.width
              implicitHeight: modelData.gradient ? gradientCard.implicitHeight : plain.implicitHeight

              Toggle {
                id: plain
                width: parent.width
                visible: !modelData.gradient
                label: modelData.name
                description: modelData.effect
                checked: modelData.enabled
                enabled: !root.busy
                hasCursor: root.selectedControl === root.deviceControl(index)
                onClicked: root.setDevice(index, !modelData.enabled)
              }

              BorderSurface {
                id: gradientCard
                width: parent.width
                visible: modelData.gradient
                radius: Style.cornerRadius
                color: Style.controlFill(false, false, Commons.Color.foreground, Commons.Color.accent)
                borderSpec: Border.controlSpec(
                  root.selectedControl === root.deviceControl(index) || root.selectedControl === root.deviceControl(index) + 1
                    ? "hover-cursor" : "normal",
                  Commons.Color.foreground,
                  Commons.Color.accent
                )
                implicitHeight: gradientBody.implicitHeight + Style.spacing.lg * 2

                Column {
                  id: gradientBody
                  anchors.left: parent.left
                  anchors.right: parent.right
                  anchors.verticalCenter: parent.verticalCenter
                  anchors.leftMargin: gradientCard.borderLeft + Style.spacing.rowPaddingX
                  anchors.rightMargin: gradientCard.borderRight + Style.spacing.rowPaddingX
                  spacing: Style.spacing.sm

                  SettingRow {
                    label: device.modelData.name
                    checked: device.modelData.enabled
                    rowEnabled: !root.busy
                    hot: root.selectedControl === root.deviceControl(device.index)
                    onClicked: root.setDevice(device.index, !device.modelData.enabled)
                  }
                  Rectangle {
                    width: parent.width
                    height: 1
                    color: Qt.darker(Commons.Color.foreground, 1.5)
                    opacity: 0.35
                  }
                  SettingRow {
                    label: strings.t("panel.gradient")
                    detail: device.modelData.effect === "gradient" ? strings.t("panel.gradientOn") : strings.t("panel.gradientOff")
                    checked: device.modelData.effect === "gradient"
                    rowEnabled: !root.busy && device.modelData.enabled
                    hot: root.selectedControl === root.deviceControl(device.index) + 1
                    onClicked: root.setEffect(device.index, device.modelData.effect === "gradient" ? "solid" : "gradient")
                  }
                }
              }
            }
          }
          Button {
            width: parent.width
            text: root.busy ? strings.t("panel.applying") : strings.t("panel.apply")
            enabled: !root.busy
            hasCursor: root.selectedControl === root.controlCount() - 1
            onClicked: root.startTask("apply", ["apply"], 45000)
          }
        }
    }
  }

  Run {
    id: task
    deadlineMs: 20000
    onFinished: result => root.finished(result)
  }
}
