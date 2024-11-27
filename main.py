import asyncio
from utils.args import args
from src.dashboard import ConsensusDashboard
from utils.logger import logger

async def start_dashboard():
    try:
        logger.info('Starting Dasboard')
        dashboard = ConsensusDashboard(
            rpc=args.rpc,
            refresh_per_second=args.refresh_per_second,
            disable_emojis=args.disable_emojis,
            refresh_validators=args.refresh_validators,
            refresh_consensus_state=args.refresh_consensus_state,
            refresh_upgarde_plan=args.refresh_upgarde_plan,
            refresh_node=args.refresh_node,
            refresh_block_time= args.refresh_block_time,
            user_tz=args.tz,
            block_time_number=args.block_time_number,
            columns=args.columns,
            hashes=args.hashes
            )
        await dashboard.start()
    except (asyncio.CancelledError, KeyboardInterrupt):
        logger.info("Dashboard interrupted")
        exit()

if __name__ == "__main__":
    asyncio.run(start_dashboard())
