package me.masonasons.fastgh.ui.components

import android.content.ActivityNotFoundException
import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.app.DownloadManager
import android.os.Build
import android.os.Environment
import android.widget.Toast
import androidx.core.net.toUri

fun Context.openUrl(url: String) {
    try {
        startActivity(Intent(Intent.ACTION_VIEW, url.toUri()))
    } catch (_: ActivityNotFoundException) {
        Toast.makeText(this, "No browser found to open $url", Toast.LENGTH_LONG).show()
    }
}

fun Context.copyToClipboard(label: String, text: String) {
    val clipboard = getSystemService(ClipboardManager::class.java)
    clipboard.setPrimaryClip(ClipData.newPlainText(label, text))
}

fun Context.shareText(text: String, title: String) {
    val intent = Intent(Intent.ACTION_SEND).apply {
        type = "text/plain"
        putExtra(Intent.EXTRA_TEXT, text)
    }
    startActivity(Intent.createChooser(intent, title))
}

/**
 * Downloads a public file to Downloads with a system notification. Before Android 10
 * that needs a storage permission, so older versions hand the link to the browser.
 */
fun Context.downloadFile(url: String, fileName: String) {
    if (Build.VERSION.SDK_INT < Build.VERSION_CODES.Q) {
        openUrl(url)
        return
    }
    val request = DownloadManager.Request(url.toUri())
        .setTitle(fileName)
        .setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED)
        .setDestinationInExternalPublicDir(Environment.DIRECTORY_DOWNLOADS, fileName)
    getSystemService(DownloadManager::class.java).enqueue(request)
}
