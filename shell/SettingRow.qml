import QtQuick
import qs.Commons
import qs.Commons as Commons
import qs.Ui

Item {
  id: row
  property string label: ""
  property string detail: ""
  property bool checked: false
  property bool rowEnabled: true
  property bool hot: false
  signal clicked()

  implicitHeight: Math.max(track.implicitHeight, labels.implicitHeight)
  width: parent ? parent.width : implicitWidth

  Row {
    anchors.left: parent.left
    anchors.right: parent.right
    anchors.verticalCenter: parent.verticalCenter
    spacing: Style.spacing.rowPaddingX

    Column {
      id: labels
      width: parent.width - track.width - parent.spacing
      anchors.verticalCenter: parent.verticalCenter
      spacing: Style.spacing.xs

      Text {
        textFormat: Text.PlainText
        text: row.label
        color: Commons.Color.foreground
        font.family: Style.font.family
        font.pixelSize: Style.font.subtitle
        font.bold: true
        elide: Text.ElideRight
        width: parent.width
        opacity: row.rowEnabled ? 1 : 0.45
      }

      Text {
        textFormat: Text.PlainText
        visible: row.detail !== ""
        text: row.detail
        color: Qt.darker(Commons.Color.foreground, 1.5)
        font.family: Style.font.family
        font.pixelSize: Style.font.caption
        wrapMode: Text.WordWrap
        width: parent.width
        opacity: row.rowEnabled ? 1 : 0.45
      }
    }

    ToggleSwitch {
      id: track
      checked: row.checked
      interactive: false
      cursorRing: true
      hasCursor: row.rowEnabled && (row.hot || rowMouse.containsMouse)
      opacity: row.rowEnabled ? 1 : 0.45
      anchors.verticalCenter: parent.verticalCenter
    }
  }

  MouseArea {
    id: rowMouse
    anchors.fill: parent
    enabled: row.rowEnabled
    hoverEnabled: true
    cursorShape: Qt.PointingHandCursor
    onClicked: row.clicked()
  }
}
