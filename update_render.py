import yaml

content = {
    'databases': [
        {
            'name': 'park4night-db',
            'databaseName': 'park4night',
            'user': 'park4night_user',
            'plan': 'free'
        }
    ],
    'services': [
        {
            'type': 'web',
            'name': 'park4night-server',
            'runtime': 'node',
            'plan': 'free',
            'buildCommand': 'npm install && cd server && npm install && npx prisma generate && npx prisma db push',
            'startCommand': 'cd server && npm start',
            'pullRequestPreviewsEnabled': 'yes',
            'envVars': [
                {'key': 'DATABASE_URL', 'fromDatabase': {'name': 'park4night-db', 'property': 'connectionString'}},
                {'key': 'NODE_ENV', 'value': 'production'},
                {'key': 'SESSION_SECRET', 'generateValue': True},
                {'key': 'GOOGLE_CLIENT_ID', 'sync': False},
                {'key': 'GOOGLE_CLIENT_SECRET', 'sync': False},
                {'key': 'CLIENT_URL', 'fromService': {'type': 'static', 'name': 'park4night-client', 'property': 'url'}}
            ]
        },
        {
            'type': 'static',
            'name': 'park4night-client',
            'buildCommand': 'npm install && cd client && npm install && npm run build',
            'publishDir': 'client/dist',
            'pullRequestPreviewsEnabled': 'yes',
            'envVars': [
                {'key': 'VITE_API_URL', 'fromService': {'type': 'web', 'name': 'park4night-server', 'property': 'url'}},
                {'key': 'VITE_GOOGLE_MAPS_API_KEY', 'sync': False}
            ]
        }
    ]
}

with open('render.yaml', 'w') as f:
    yaml.dump(content, f, sort_keys=False)
