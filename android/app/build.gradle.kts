plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.compose)
    alias(libs.plugins.kotlin.serialization)
}

// The version is the desktop app's (version.py); the build number is the count of
// commits, so each build is higher than the last, as in FastPlay.
val appVersion: String = rootProject.file("../version.py").readLines()
    .firstOrNull { it.startsWith("APP_VERSION") }
    ?.substringAfter('"')?.substringBefore('"') ?: "0.0.0"
val buildNumber: Int = runCatching {
    providers.exec { commandLine("git", "rev-list", "--count", "HEAD") }
        .standardOutput.asText.get().trim().toInt()
}.getOrDefault(1)

fun secret(name: String): String? = (project.findProperty(name) as String?) ?: System.getenv(name)

android {
    namespace = "me.masonasons.fastgh"
    compileSdk = 37

    defaultConfig {
        applicationId = "me.masonasons.fastgh"
        minSdk = 26
        targetSdk = 36
        versionCode = buildNumber
        versionName = appVersion
    }

    // The release keystore and its passwords come from Gradle properties or the
    // environment (CI's secrets), never the repository. Without them a release
    // build is signed with the debug key: fine to try, not to publish.
    signingConfigs {
        create("release") {
            val store = secret("ANDROID_KEYSTORE_FILE")
            val storePass = secret("ANDROID_KEYSTORE_PASSWORD")
            val alias = secret("ANDROID_KEY_ALIAS")
            val keyPass = secret("ANDROID_KEY_PASSWORD")
            if (store != null && storePass != null && alias != null && keyPass != null) {
                storeFile = file(store)
                storePassword = storePass
                keyAlias = alias
                keyPassword = keyPass
            }
        }
    }

    buildTypes {
        release {
            signingConfig = signingConfigs.getByName("release").takeIf { it.storeFile != null }
                ?: signingConfigs.getByName("debug")
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    buildFeatures {
        compose = true
    }
}

dependencies {
    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.activity.compose)
    implementation(libs.androidx.navigation.compose)
    implementation(libs.androidx.lifecycle.runtime.compose)
    implementation(libs.androidx.lifecycle.viewmodel.compose)
    implementation(platform(libs.compose.bom))
    implementation(libs.compose.ui)
    implementation(libs.compose.ui.tooling.preview)
    implementation(libs.compose.material3)
    implementation(libs.compose.material.icons)
    implementation(libs.okhttp)
    implementation(libs.kotlinx.serialization.json)
    implementation(libs.kotlinx.coroutines.android)
    debugImplementation(libs.compose.ui.tooling)

    testImplementation(libs.junit)
    testImplementation(libs.okhttp.mockwebserver)
    testImplementation(libs.kotlinx.coroutines.test)
}
