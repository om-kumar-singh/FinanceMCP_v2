import { initializeApp, getApps, getApp, type FirebaseApp } from 'firebase/app'
import { getAuth, type Auth } from 'firebase/auth'
import { getAnalytics, isSupported, type Analytics } from 'firebase/analytics'
import { getDatabase, type Database } from 'firebase/database'

const firebaseConfig = {
  apiKey: 'AIzaSyDHPMqWmnZGBvalrRQ4ccim-Y3tm-LUr3A',
  authDomain: 'financemcp-4d400.firebaseapp.com',
  projectId: 'financemcp-4d400',
  storageBucket: 'financemcp-4d400.firebasestorage.app',
  messagingSenderId: '393265429143',
  appId: '1:393265429143:web:c4e4a8de143266f92c07d2',
  measurementId: 'G-S40P9V48V0',
}

let app: FirebaseApp
if (!getApps().length) {
  app = initializeApp(firebaseConfig)
} else {
  app = getApp()
}

console.log('Firebase App Name:', app.name)
console.log('Config Project ID:', firebaseConfig.projectId)

const auth: Auth = getAuth(app)
const db: Database = getDatabase(app)

let analytics: Analytics | undefined

if (typeof window !== 'undefined') {
  // Analytics is optional and only works in the browser
  isSupported()
    .then((supported) => {
      if (supported) {
        analytics = getAnalytics(app)
      }
    })
    .catch(() => {
      // ignore analytics errors
    })
}

export { app, auth, db, analytics }

